# serial_vcr
serial_vcr provides a simple interface for controlling a JVC SR-S365U V
ideo Cassette Recorder over a serial port from Python (2.x).

# Requirements 

* No specific OS requirements: Only tested on Windows 10 so far, but it should be cross-platform.
* Python 2.x (Tested on 2.7.15)
* The py_serial module (https://pypi.org/project/pyserial/)

# Usage

import serial_vcr, create a VCR object with the port (and optional baud rate), and then call vcr.oneshot using various constant for commands.

Example:

    import serial_vcr
    vcr = serial_vcr.VCR('COM2')
    vcr.oneshot(serial_vcr.PLAY)


# License

The code is under the GPL version 3, the documentation in the docs/ subdir is copyrighted by JVC.