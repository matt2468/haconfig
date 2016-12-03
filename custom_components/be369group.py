"""
 Working on setting zwave lock codes and storing name references for entries
"""
import logging
import collections

import homeassistant.helpers.config_validation as cv
import homeassistant.components.zwave.const as zconst
from homeassistant.components import persistent_notification
from homeassistant.components import logbook
import voluptuous as vol
from pydispatch import dispatcher
from openzwave.option import ZWaveOption
from openzwave.network import ZWaveNetwork
from openzwave.group import ZWaveGroup


_LOGGER = logging.getLogger(__name__)
DEPENDENCIES = ['zwave']
DOMAIN = 'be369group'
LOCKGROUP = None

USER_CODE_ENTERED = 16
TOO_MANY_FAILED_ATTEMPTS = 96
NOT_USER_CODE_INDEXES = (0, 254, 255)  # Enrollment code, refresh and code count


def setup(hass, config):
    """ Thanks to dispatcher being globally available in the application, we can hook in from here """
    global LOCKGROUP
    LOCKGROUP = BE369LockGroup(hass) 
    dispatcher.connect(LOCKGROUP.valueadded, ZWaveNetwork.SIGNAL_VALUE_ADDED)
    dispatcher.connect(LOCKGROUP.valuechanged, ZWaveNetwork.SIGNAL_VALUE_CHANGED)
    return True


class BE369LockGroup:
    """
        Group all the locks info together so we can set the same code in the same slot on each lock.

        I think this BE369 use of alarms is entirely specific to this old lock, there appears to be an actual
        lock logging class for newer zwave devices.  Ah, corner cases, my old friend.

        The default HA ZWaveAlarmSensor treats zwave alarms as separate state values and therefore won't send
        updates if the same door code entered multiple times in succession, hence this little snippet.

        We also have to resort to ugliness to get the data about UserCode availability.  I may try to fix this
        myself and submit a patch to the openzwave group later.

        This has becomes pretty much all specific case work.
    """

    def __init__(self, hass):
        self.hass   = hass
        self.codes  = collections.defaultdict(list)  # index  -> [values]
        self.alarms = dict()                         # nodeid -> [alarmtype, alarmval]


    def lockactivity(self, nodeid, atype, aval):
        """ We have decoded a report (via alarms) from the BE369 lock """
        if atype == USER_CODE_ENTERED:
            logbook.log_entry(self.hass, "LockNameHere", 'User entered door code (node={}, slot={})'.format(nodeid, aval))

        elif atype == TOO_MANY_FAILED_ATTEMPTS:
            msg = 'Multiple invalid door codes enetered at node {}'.format(nodeid)
            persistent_notification.create(self.hass, msg, 'Potential Prowler')
            _LOGGER.warning(msg)

        else:
            _LOGGER.warning("Unknown lock alarm type! Investigate ({}, {}, {})".format(nodeid, atype, aval))


    def extractUserCodeStatus(self, value):
        """
          Get ready for this, the command class (UserCode) info doesn't bubble up through pyopenzwave
          so I have to find the last received message data for the node and extract UserCodeStatus manually.
          Not pretty but thank god I have open source code to look through.  I'll wager this is probably
          not an interface to depend on either.
        """
        value.available = not value.network.manager.getNodeStatistics(value.home_id, value.parent_id)['lastReceivedMessage'][8]
        _LOGGER.debug("{} code {} available {}".format(value.parent_id, value.index, value.available))


    def valueadded(self, node, value):
        """ Make note of any user code entries on generic locks """
        if (node.generic == zconst.GENERIC_TYPE_ENTRY_CONTROL and
            value.command_class == zconst.COMMAND_CLASS_USER_CODE and
            value.index not in NOT_USER_CODE_INDEXES):

            _LOGGER.debug("registered usercode {}, {} on {}".format(value.index, value.label, value.parent_id))
            value.available = None # unknown status
            self.codes[value.index].append(value)
            self.alarms[value.parent_id] = [None]*2


    def valuechanged(self, value):
        """ We look for usercode and alarm messages from our locks here """
        if value.command_class == zconst.COMMAND_CLASS_USER_CODE:
            self.extractUserCodeStatus(value)

        elif value.parent_id in self.alarms and value.command_class == zconst.COMMAND_CLASS_ALARM:
            _LOGGER.debug("alarm piece {} {} on {}".format(value.index, value.data, value.parent_id))
            try:
                # OpenZwave breaks the single code/data alarm message into two values so we collect/reset here
                bits = self.alarms[value.parent_id]
                bits[value.index] = value.data
                if None not in bits:  
                    self.lockactivity(value.parent_id, bits[0], bits[1])
                    bits[:] = [None]*2

            except Exception as e:
                _LOGGER.error("exception {}: got bad data? index={}, data={}".format(e, value.index, value.data))

