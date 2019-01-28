import serial,sys

class BadResponseError(ValueError):
	pass

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

class VCR(object):
	def __init__(self, port, baud = 9600):
		self.vcr = serial.Serial(port, baud)
		# I don't fully understand the distrinction between table 1 / table 2
		# but some commands do not work in table 2, so just in case we're 
		# stuck in table 2, let's switch to table 1 first to be sure.
		self.oneshot(JVC_TABLE_1)

	def is_a_vcr(self):
		return self.converse(VCR_INQ) == chr(ACK)

	def device_type(self):
		return self.converse(DEVICE_TYPE_REQUEST, 4)

	def rom_version(self):
		return self.converse(ROM_VER_REQUEST, 3)

	def oneshot(self, command):
		ret = self.converse(command)
		if ret != '\x0A':
			raise BadResponseError("Expected ACK, got {}".format(ret.encode('hex')))

	def converse(self, command, num_bytes=1):
		vcr = self.vcr
		vcr.write(chr(command))
		return vcr.read(num_bytes)


if __name __ == '__main__':
	vcr = VCR(sys.argv[1])
	if vcr.is_a_vcr():
		print 'Yes, it is a VCR'
		print "It's a {} running rom version {:}".format(vcr.device_type(), vcr.rom_version().encode('hex'))
	else:
		print 'WARNING: NOT A VCR! POSSIBLY A DECEPTICON! RUN!'

