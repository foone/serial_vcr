import serial, sys, time


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


class BadResponseError(Exception):
	def __init__(self, expected, got):
		message = 'Expected {}, got {}'.format(hexify(expected),hexify(got))
		Exception.__init__(self, message)
		self.expected = expected
		self.got = got

def translate_bits(num_or_char, bit_meanings):
	num = numify(num_or_char)
	out = []
	for i,meaning in enumerate(bit_meanings):
		if ((1<<i) & num) and meaning is not None:
			out.append(meaning)
	return out 

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

	def oneshot(self, command):
		ret = self.converse(command)
		if ret != '\x0A':
			raise BadResponseError(ACK, ret)

	def converse(self, command, num_bytes=1):
		vcr = self.vcr
		vcr.write(chr(command))
		data = vcr.read(num_bytes)
		# per the spec, you have to wait at least 5 msec after getting a 
		# response before sending another command
		# TODO: be smarter about this, and only wait if needed.
		time.sleep(0.005)
		return data


if __name__ == '__main__':
	vcr = VCR(sys.argv[1])
	if vcr.is_a_vcr():
		print 'Yes, it is a VCR'
		print "It's a {} running rom version {:}".format(vcr.device_type(), vcr.rom_version().encode('hex'))
	else:
		print 'WARNING: NOT A VCR! POSSIBLY A DECEPTICON! RUN!'
	vcr.oneshot(POWER_ON)
	print vcr.status_sense()