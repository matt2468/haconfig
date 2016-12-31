import re
import threading
from base64 import b64decode
from email.parser import BytesParser

from twisted.internet.protocol import Factory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor

# hrrm, what about other unknown components who used twisted reactor?  A shortfall of their setup...

class AmcrestSmtpReactor(threading.Thread):
    """ Wrapper for the factory and to keep 'library' code our of component """
    """ I'm not sure how best to deal with Twisted's global reactor, for now I assume """
    """ I'm the only one using it """
    def __init__(self, port, callback):
        threading.Thread.__init__(self, daemon=True)
        self.factory = SMTPFactory(callback)
        reactor.listenTCP(port, self.factory)

    def run(self):
        reactor.run(installSignalHandlers=0)

    def stop(self):
        reactor.stop()


class SMTPFactory(Factory):
    """ This factory just passes the callback and connecting address to each connection """
    def __init__(self, callback):
        self.callback = callback
    def buildProtocol(self, addr):
        return SMTPReceiver(addr, self.callback)


class SMTPReceiver(LineReceiver):
    """
        Unfortunatly, the Email portion of Twisted is not python3 compliant yet so
        I had to create my own.  I cheat and only do the things necessary for an Amcrest
        camera to send me the data.  I don't really care about anything but that.
    """

    def __init__(self, addr, callback):
        self.addr = addr
        self.callback = callback
        self.state = None
        self.msg = b''

    def processMessage(self):
        parts = BytesParser().parsebytes(self.msg).get_payload()
        if len(parts) > 0:
            msg = b64decode(parts[0].get_payload())
            match = re.search(b'Alarm Event: (\w+)', msg)
            if match is not None:
                # event is (Mail_Test, Illegal, Tamper, Motion, etc)
                self.callback(event=match.group(1), addr=self.addr.host)

        # Do we want to store snapshots? Below does that
        #if len(parts) > 1:
            #fp = open('/tmp/'+parts[1].get_filename(), 'wb')
            #fp.write(b64decode(parts[1].get_payload()))
            #fp.close()

    def connectionMade(self):
        self.sendLine(b'220')

    def lineReceived(self, data):
        head = data[0:4] 
        # User/Passhead states
        if   self.state == "user":       self.sendLine(b'334 UGFzc3dvcmQ6'); self.state = "pass"
        elif self.state == "pass":       self.sendLine(b'235');              self.state = None
        # Just respond , don't care about state
        elif head in (b'HELO', b'EHLO'): self.sendLine(b'250 Hello ' + data.split()[1])
        elif head in (b'AUTH'):          self.sendLine(b'334 VXNlcm5hbWU6'); self.state = "user"
        elif head in (b'MAIL', b'RCPT'): self.sendLine(b'250')
        elif head in (b'QUIT'):          self.sendLine(b'221');              self.transport.loseConnection()
        elif head in (b'DATA'):          self.sendLine(b'354');              self.msg = b''; self.setRawMode()
        else:                            self.sendLine(b'500')

    def rawDataReceived(self, data):
        self.msg += data
        if self.msg.endswith(LineReceiver.delimiter + b'.' + LineReceiver.delimiter):
            self.sendLine(b'250')
            self.setLineMode()
            self.processMessage()


if __name__ == '__main__':
    def cb(**kwargs):
        print("callback {}".format(kwargs))
    x = AmcrestSmtpReactor(2525, cb)
    x.start()
 
