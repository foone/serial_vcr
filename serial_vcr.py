import serial, sys, time, datetime


ACK                 = 0x0A
NAK                 = 0x0B
ERROR               = 0x02
CLEAR               = 0x56
CLEAR_ERROR         = 0x41

FF                  = 0xAB
REW                 = 0xAC
STOP                = 0x3F
EJECT               = 0xA3
CASSETTE_OUT        = 0x03
PLAY                = 0x3A
STILL               = 0x4F

COUNTER_RESET       = 0xE2
CURRENT_CTL_SENSE   = 0xD9
CURRENT_LTC_SENSE   = 0xDC
ENTER               = 0x40


STATUS_SENSE        = 0xD7
JVC_STATUS_SENSE    = 0xDD

VCR_INQ             = 0xFB
DEVICE_TYPE_REQUEST = 0xD1
ROM_VER_REQUEST     = 0x72

JVC_TABLE_1         = 0xF6
JVC_TABLE_2         = 0xF7

POWER_ON            = 0x7B
POWER_OFF           = 0x7C
#TODO: reverse lookup table, for better error messages.


# From pages 38-39 of the service manual
STATUS_SENSE_MODE_BITS=(
	# Byte 1
	( 
		'ERROR',        # An unacceptable command has been received. Any subsequent 
		                # commands will have no effect. To clear this condition, send
		                # CLEAR_ERROR (41)
		None,           # Not defined
		None,           # SERVO LOCK, always 1
		'CASSETTE OUT', # No cassette is loaded
		'REC INHIBIT',  # The tape is read-only and can't be recorded to. 
		                # Note: The manual says "The loaded cassette does 
		                # not have a protective tab" which is kinda backwards 
		                # and confusing.
		'SHORT FF/REW', # After detecting the beginning and end of the tape,
		                # the VCR enters the SHORT FF or SHORT REW mode.
		None,           # Always 0
		None            # Always 1
	),
	# Byte 2
	( 
		'TAPE END',     # The end of tape is detected.
		'TAPE BEGIN',   # The beginning of the tape is detected.
		None,           # DEW: Not available
		'WARNING',      # Warns of a problem with the VCR
		'AUDIO MUTE',   # Audio signals are muted
		'VIDEO MUTE',   # Video signals are muted
		'A1 EE MODE',   # EE output for audio 1 output.
		'EE MODE'       # EE output for video output
	),
	# Byte 3
	( 
		None,           # Not defined
		'SEARCH MODE',  # In search (CUE UP/MEMORY SEARCH)
		'REPEAT MODE',  # In repeat
		None,           # Not defined
		'REPEAT',       # The VCR's repeat mode is set to on
		                # NOTE: the manual has a confusing note here:
		                # For communications via by RS-232C, check to see if the bit is 0.
		                # if not, change the relevant setting to make it 0.
		None,           # COUNTER SEARCH: Not available
		None,           # TIMER REC ON: Not available
		None            # TIMER PLAY ON: Not available
	),
	# Byte 4
	(
		'AUDIODUB',     # In post-recording mode
		'REC',          # Record
		'EJECT',        # The cassette is being ejected.
		'STANDBY',      # Stop (Not a typo. The manual defines both bits as just STOP)
		'STOP',         # Stop
		'REW',          # Rewind
		'FF',           # Fast forward
		'PLAY'          # Playback (note: In the STILL, REC, ASSEMBLE, INSERT, and AUDIODUB modes
		                # this bit is also 1)
	),
	# Byte 5
	(
		None,           # Bits 0-3 are used for the SPEED CODE, see SPEED_TABLE below
		None,
		None,
		None,
		'SHUTTLE REV',  # Reverse shuttle search
		'SHUTTLE FWD',  # Forward shuttle saerch
		'LONG PAUSE',   # Long Pause (tape protection)
		'PAUSE'         # Pause
	)
)

SPEED_TABLE = (
	'STILL',
	'1/30',
	'1/18',
	'1/6',
	'INVALID(4)'        # 4 is missing from the table for unknown reasons
	'1',
	'2(-3)',            # Forward direction: +2x, reverse direction: -3x
	'5',
	'7',
	'11',
	'15',
	'24',               # x24 (or more)
	'INVALID(C)',       # The table only defines entries up through 0xB, so 
	'INVALID(D)',       # C/D/E/F are presumably invalid and impossible.
	'INVALID(E)',
	'INVALID(F)'
)

# From wikipedia: https://en.wikipedia.org/wiki/NTSC#Frame_rate_conversion
NTSC_FRAME_RATE = 10000000.*63/88/455/525            # end result: ~29.97
FRAMES_PER_MILLISECOND = NTSC_FRAME_RATE / 1000.0    # ~0.02996
MILLSECONDS_PER_FRAME = 1.0 / FRAMES_PER_MILLISECOND # ~33.38

def hexify(s):
	if isinstance(s, basestring):
		return s.encode('hex').upper()
	else:
		return '{:02X}'.format(s)

def numify(s):
	if isinstance(s, basestring):
		return ord(s)
	else:
		return s

class VCRException(Exception):
	pass

class BadResponseError(VCRException):
	def __init__(self, expected, got):
		message = 'Expected {}, got {}'.format(hexify(expected),hexify(got))
		Exception.__init__(self, message)
		self.expected = expected
		self.got = got

class ErrorWhileReadingError(VCRException):
	def __init__(self, got):
		message = 'got {} when reading response'.format(hexify(got))
		Exception.__init__(self, message)
		self.got = got

def translate_bits(num_or_char, bit_meanings):
	num = numify(num_or_char)
	out = []
	for i,meaning in enumerate(bit_meanings):
		if ((1<<i) & num) and meaning is not None:
			out.append(meaning)
	return out 

class VCRTime(object):
	def __init__(self, raw_time):
		self.raw_time = raw_time

	@property
	def hours(self):
		return int(self.raw_time[0:2])

	@property
	def minutes(self):
		return int(self.raw_time[2:4])

	@property
	def seconds(self):
		return int(self.raw_time[4:6])

	@property
	def frames(self):
		return int(self.raw_time[6:8])

	@property
	def timedelta(self):
		return datetime.timedelta(
			hours=self.hours, 
			minutes = self.minutes, 
			seconds= self.seconds, 
			milliseconds=self.frames*MILLSECONDS_PER_FRAME
		)

	def __repr__(self):
		return 'VCRTime({0.hours}h, {0.minutes}m, {0.seconds}s, {0.frames} frames)'.format(self)

class VCR(object):
	def __init__(self, port, baud = 9600):
		self.vcr = serial.Serial(port, baud)
		# I don't fully understand the distrinction between table 1 / table 2
		# but some commands do not work in table 2, so just in case we're 
		# stuck in table 2, let's switch to table 1 first to be sure.
		try:
			self.oneshot(JVC_TABLE_1)
		except BadResponseError:
			# It might be turned off, in which case we'll get a NAK
			pass 

	def is_a_vcr(self):
		return self.converse(VCR_INQ) == chr(ACK)

	def device_type(self):
		return self.converse(DEVICE_TYPE_REQUEST, 4)

	def rom_version(self):
		return self.converse(ROM_VER_REQUEST, 3)

	def status_sense(self):
		data = self.converse(STATUS_SENSE, 5)
		modes = []
		for i, status_byte in enumerate(STATUS_SENSE_MODE_BITS):
			modes.extend(translate_bits(data[i], status_byte))
		SPEED  = SPEED_TABLE[ord(data[4]) & 0xF]
		return modes + [SPEED]


	def rewind_to_beginning(self):
		self.oneshot(REW)
		self.wait_until_mode('REW', timeout = 10)
		self.wait_until_mode('STOP')
		# TODO: Should we have some kind of timeout for STOP?
		# What if the VCR errors out and powers off?

	def play_to_end(self):
		self.oneshot(PLAY)
		self.wait_until_mode('PLAY', timeout = 10)
		self.wait_until_mode('STOP')
		# TODO: Should we have some kind of timeout for STOP?
		# What if the VCR errors out and powers off?

	def get_ctl_time(self):
		return VCRTime(self.converse(CURRENT_CTL_SENSE, 8, check=True))
	
	def get_ltc_time(self):
		return VCRTime(self.converse(CURRENT_LTC_SENSE, 8, check=True))

	def wait_until_mode(self, mode, timeout = None):
		abort_time = None if timeout is None else time.time() + timeout
		while mode not in self.status_sense():
			time.sleep(1)
			if abort_time is not None and abort_time>time.time():
				return False
		return True

	def oneshot(self, command):
		ret = self.converse(command)
		if ret != '\x0A':
			raise BadResponseError(ACK, ret)

	def converse(self, command, num_bytes=1, check=False):
		vcr = self.vcr
		try:
			vcr.write(chr(command))
			if check:
				# if we're expecting a multibyte reply and it instead returns 
				# an error, we'd otherwise hang waiting forever for a reply
				# that isn't comming. So check if the first byte is an error.
				# This assumes that the first byte can never legitimately be 
				# NAK or ERROR, though! 

				first_byte = vcr.read(1)
				if ord(first_byte) in (NAK, ERROR):
					raise ErrorWhileReadingError(first_byte)
				if num_bytes>1:
					data = vcr.read(num_bytes-1)
					return first_byte + data
				else:
					return first_byte
			else:
				return vcr.read(num_bytes)
		finally:
			# per the spec, you have to wait at least 5 msec after getting a 
			# response before sending another command
			# TODO: be smarter about this, and only wait if needed.
			time.sleep(0.005)


if __name__ == '__main__':
	vcr = VCR(sys.argv[1])
	if vcr.is_a_vcr():
		print 'Yes, it is a VCR'
		print "It's a {} running rom version {:}".format(vcr.device_type(), vcr.rom_version().encode('hex'))
	else:
		print 'WARNING: NOT A VCR! POSSIBLY A DECEPTICON! RUN!'
	vcr.oneshot(POWER_ON)
	if 0:
		vcr.rewind_to_beginning()
		
		start = time.time()
		vcr.oneshot(FF)
		time.sleep(5)
		vcr.wait_until_mode('STOP')
		print 'went to end in {:0.2f} seconds'.format(time.time()-start)

	current_time = vcr.get_ctl_time()
	print current_time

