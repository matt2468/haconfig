"""
 Support for my little custom I/O board from years ago
"""
import logging
import re
import serial
import serial.threaded

import voluptuous as vol

from homeassistant.const import ( EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP)
from homeassistant.const import CONF_PORT
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['pyserial>=3.1.1']
_LOGGER = logging.getLogger(__name__)
BOARD = None
DOMAIN = 'bwio'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_PORT): cv.string,
    }),
}, extra=vol.ALLOW_EXTRA)


def setup(hass, config):
    """ Setup the BWIO interface """
    global BOARD
    try:
        BOARD = BWIOBoard(config[DOMAIN][CONF_PORT])
    except (serial.serialutil.SerialException, FileNotFoundError):
        _LOGGER.exception("BWIO port (%s) is not accessible." % (config[DOMAIN][CONF_PORT]))
        return False

    hass.bus.listen_once(EVENT_HOMEASSISTANT_START, lambda e: BOARD.ping())
    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, lambda e: BOARD.close())
    return True


class BWIOBoard(serial.threaded.LineReader):
    """ Representation of an BWIO board. """

    def __init__(self, port):
        """ Connect to the board. """
        super(serial.threaded.LineReader, self).__init__()
        self._inputs = list()
        self._outputs = list()
        self._thread = serial.threaded.ReaderThread(serial.Serial(port), self)
        self._thread.start()

    def __call__(self):
        """ Force pyserial ReaderThread to just keep using us as the protocol object """
        return self  

    def register_input(self, dev):
        self._inputs.append(dev)

    def register_output(self, dev):
        self._outputs.append(dev)

    def ping(self):
        self.ping_input()
        self.ping_output()
        self.ping_samplerate()

    def ping_input(self):
        self.send("I")
        
    def ping_output(self):
        self.send("O")

    def ping_samplerate(self):
        self.send("S")

    def set_output(self, pin, val):
        self.send("O%X=%X" % (pin, val))

    def send(self, data):
        _LOGGER.debug("Sending data (%s)", data)
        self.write_line(data)

    def handle_line(self, line):
        _LOGGER.debug("Received data (%s)", line.strip())
        ins = re.match(r"I=([0-9,A-F]+)", line)
        if ins is not None:
            val = int(ins.group(1), 16)
            for dev in self._inputs:
                dev.new_input_data(val)

        outs = re.match(r"O=([0-9,A-F]+)", line)
        if outs is not None:
            val = int(outs.group(1), 16)
            for dev in self._outputs:
                dev.new_output_data(val)

    def close(self):
        _LOGGER.info("Closing port")
        self._thread.close()

