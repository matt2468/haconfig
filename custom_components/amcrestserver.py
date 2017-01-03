import logging
import time
import socket
import threading
import json
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)
CONNECTION = None
DOMAIN = 'amcrestserver'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({}),
}, extra=vol.ALLOW_EXTRA)

def setup(hass, config):
    """ Setup a TCP connection to the amcrest server.  KISS, sudden TCP connection closes at shutdown are just fine here """
    global CONNECTION
    CONNECTION = AmcrestServerConnection()
    CONNECTION.start()
    return True

class AmcrestServerConnection(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self, daemon=True)
        self.sock = None
        self.devices = list()
        
    def run(self):
        """Send a command to the pa server using a socket."""
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect(('127.0.0.1', 2626))
                _LOGGER.debug("Connected")

                while True:
                    result = ""
                    eol = -1

                    while eol < 0:
                        result += self.sock.recv(1024).decode('utf-8')
                        eol = result.find("\r\n")

                    self.handle_data(json.loads(result[:eol]))
                    result = result[eol+2:]

            except Exception as e:
                _LOGGER.warning("AmcrestServer Exception {}".format(e))
                try: self.sock.close()
                except: pass
                time.sleep(5)
                
    def add_device(self, dev):
        self.devices.append(dev)
        self.sock.send(b'\r\n')  # Ping for updated info

    def handle_data(self, data):
        _LOGGER.info("Received data {}".format(data))
        for sensor in self.devices:
            for addr in data:
                if addr == sensor._addr:
                    sensor.new_data(data[addr])

