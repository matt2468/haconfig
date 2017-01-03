#!/usr/bin/env python2

"""
    Provides three servers:
        1 - FTP Server to receive Amcrest Camera Videos
        2 - SMTP Server to receive other Amcrest Camera Email alerts
        3 - Simple TCP Line receiver to push events to HA
"""

from twisted.mail.smtp import ESMTP, SMTPFactory, IMessageDelivery
from twisted.mail.imap4 import LOGINCredentials, PLAINCredentials
from twisted.protocols.ftp import FTPFactory, IFTPShell, FTPShell, FTP, CmdNotImplementedForArgError, PermissionDeniedError
from twisted.protocols.ftp import CMD_OK, REQ_FILE_ACTN_COMPLETED_OK
from twisted.protocols.basic import LineReceiver
from twisted.cred.portal import Portal
from twisted.cred.checkers import FilePasswordDB
from twisted.internet.protocol import Factory
from twisted.internet import reactor, defer
from twisted.python import filepath
from twisted.logger import Logger, globalLogPublisher, FilteringLogObserver, textFileLogObserver, LogLevelFilterPredicate, LogLevel

from email.parser import Parser
from datetime import datetime
from base64 import b64decode
import json
import subprocess
import os
import re
import sys


VIDEOROOT = "/var/video"
CAMERAS = {
    '192.168.2.3': { 'motion': 'off', 'event': '', 'path': '/var/video/driveway'  },
    '192.168.2.4': { 'motion': 'off', 'event': '', 'path': '/var/video/frontyard' }
}


""" FTP Services """

class MonitoredFTP(FTP):
    """
        FTP Protocol that operates on file uploads, overrides the following ...
        ALLO and REST to make the Amcrest client happy
        STOR to use as motion on
        RNTO to use as motion off and hook to rename, snap
    """

    def ftp_ALLO(self, arg):
        return (CMD_OK,)

    def ftp_REST(self, arg):
        try:
            pos = int(arg)
            assert pos == 0           
        except:
            return defer.fail(CmdNotImplementedForArgError(arg))
        self.sendLine("350 Restarting at 0")

    def ftp_STOR(self, path):
        host = self.transport.getPeer().host
        if host in CAMERAS and path.endswith('mp4_'):
            log.info("CAMERA {}, motion on".format(host))
            CAMERAS[host]['motion'] = 'on'
            hafactory.doupdate()
        return FTP.ftp_STOR(self, path)

    def ftp_RNTO(self, toName):
        fromName = self._fromName
        del self._fromName
        self.state = self.AUTHED

        try:
            host = self.transport.getPeer().host
            fp   = os.path.join(os.path.join(VIDEOROOT, *self.workingDirectory), fromName)

            if host in CAMERAS and toName.endswith('mp4'):
                parts   = re.split('[-\[\]]', toName)
                start   = datetime.strptime(parts[0], '%H.%M.%S')
                end     = datetime.strptime(parts[1], '%H.%M.%S')
                diff    = end - start
                newname = "{}_{}_{}s.mp4".format(self.workingDirectory[1], parts[0].replace('.',':'), diff.seconds)

                CAMERAS[host]['motion'] = 'off'
                log.info("CAMERA {}, motion off".format(host))
                hafactory.doupdate()
                tp = os.path.join(CAMERAS[host]['path'], newname)
                log.debug("rename {} to {}".format(fp, tp))
                os.rename(fp, tp)
                log.info("snapshot {}".format(tp))
                subprocess.Popen(["snapshot", tp]).pid
            else:
                log.info("deleting {}".format(fp))
                os.remove(fp)

        except Exception, e:
            log.failure("Whoops: {}".format(e))
            return defer.fail(PermissionDeniedError(toName))

        return defer.succeed(None).addCallback(lambda ign: (REQ_FILE_ACTN_COMPLETED_OK,))


""" SMTP Services, this just gets non video alarms like password, SD card error, etc """

class ConsoleMessage:
    def __init__(self):           self.lines = []
    def connectionLost(self):     self.lines = None
    def lineReceived(self, line): self.lines.append(line)
    def eomReceived(self):
        """ Now we can parse the data and extract the alarm type """
        host = self.lines.pop(0)
        if host not in CAMERAS:
            return defer.succeed(None)

        parts = Parser().parsestr("\n".join(self.lines)).get_payload()
        if len(parts) > 0:
            msg = b64decode(parts[0].get_payload())
            match = re.search(b'Alarm Event: (\w+)', msg)
            if match is not None:
                CAMERAS[host]['event'] = match.group(1)
                log.info("CAMERA {}, event {}".format(host, match.group(1)))
                hafactory.doupdate()
        self.lines = None
        return defer.succeed(None)

class ConsoleMessageDelivery:
    def receivedHeader(self, helo, origin, recipients): return helo[1]
    def validateFrom(self, helo, origin): return origin
    def validateTo(self, user): return lambda: ConsoleMessage()

class ConsoleSMTPFactory(SMTPFactory):
    protocol = ESMTP
    def buildProtocol(self, addr):
        p = SMTPFactory.buildProtocol(self, addr)
        p.challengers = {"LOGIN": LOGINCredentials, "PLAIN": PLAINCredentials}
        return p


""" Home Assistant Interface, not much, just push data """

class HAFactory(Factory):
    def __init__(self):
        self.clients = []
    def buildProtocol(self, addr):
        log.info("HA Connect")
        self.clients.append(HAConnection(self))
        return self.clients[-1]
    def connectionLost(self, client):
        log.info("HA Disconnect")
        self.clients.remove(client)
    def doupdate(self):
        log.info("HA Update {}".format(len(self.clients)))
        for c in self.clients:
            c.sendStatus()

class HAConnection(LineReceiver):
    def __init__(self, factory):   self.factory = factory
    def sendStatus(self):          self.sendLine(json.dumps(CAMERAS))
    def connectionMade(self):      self.sendStatus()
    def lineReceived(self, ign):   self.sendStatus()
    def connectionLost(self, ign): self.factory.connectionLost(self)


""" Put it all together """

class AmcrestRealm:
    def requestAvatar(self, avatarId, mind, *interfaces):
        if IFTPShell in interfaces:
            return (IFTPShell, FTPShell(filepath.FilePath(VIDEOROOT)), lambda: None)
        if IMessageDelivery in interfaces:
            return (IMessageDelivery, ConsoleMessageDelivery(), lambda: None)

        raise NotImplementedError("Unable to provide avatar for interfaces provided ({})".format(interfaces))


log = Logger("amcrest")
predicate = LogLevelFilterPredicate(LogLevel.warn)
predicate.setLogLevelForNamespace("amcrest", LogLevel.debug)
globalLogPublisher.addObserver(FilteringLogObserver(textFileLogObserver(sys.stderr), (predicate,)))

portal = Portal(AmcrestRealm(), [FilePasswordDB(os.path.join(os.path.dirname(os.path.abspath(__file__)), "passwords.txt"))])

ftpfactory = FTPFactory(portal)
ftpfactory.allowAnonymous = False
ftpfactory.protocol = MonitoredFTP

hafactory = HAFactory()

reactor.listenTCP(2121, ftpfactory)
reactor.listenTCP(2525, ConsoleSMTPFactory(portal))
reactor.listenTCP(2626, hafactory, interface='127.0.0.1') 
reactor.run()

