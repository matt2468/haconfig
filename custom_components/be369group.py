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
    """

    def __init__(self, hass):
        self.hass   = hass
        self.codes  = collections.defaultdict(list)  # index  -> [values]
        self.alarms = dict()                         # nodeid -> [alarmtype, alarmval]

    def lockactivity(self, nodeid, atype, aval):
        if atype == USER_CODE_ENTERED:
            msg = 'User entered door code (node={}, slot={})'.format(nodeid, aval)
            _LOGGER.info(msg)

        elif atype == TOO_MANY_FAILED_ATTEMPTS:
            msg = 'Multiple invalid door codes enetered at node {}'.format(nodeid)
            _LOGGER.warning(msg)
            persistent_notification.create(self.hass, msg, 'Potential Prowler')

        else:
            msg = "Unknown lock alarm type! Investigate ({}, {}, {})".format(nodeid, atype, aval)
            _LOGGER.warning(msg)

        logbook.log_entry(self.hass, "LockNameHere", msg)


    def valueadded(self, node, value):
        """ Make note of any user code entries on generic locks """
        if (node.generic == zconst.GENERIC_TYPE_ENTRY_CONTROL and
            value.command_class == zconst.COMMAND_CLASS_USER_CODE and
            value.index not in NOT_USER_CODE_INDEXES):
              _LOGGER.debug("registered usercode %s, %s on %s" % (value.index, value.label, value.parent_id))
              self.codes[value.index].append(value)
              self.alarms[value.parent_id] = [None]*2


    def valuechanged(self, value):
        """ We look for alarm messages from our locks here """
        if value.parent_id in self.alarms and value.command_class == zconst.COMMAND_CLASS_ALARM:
            _LOGGER.debug("alarm piece %s %s on %s" % (value.index, value.data, value.parent_id))
            try:
                # OpenZwave breaks the single code/data alarm message into two values so we collect/reset here
                bits = self.alarms[value.parent_id]
                bits[value.index] = value.data
                if None not in bits:  
                    self.lockactivity(value.parent_id, bits[0], bits[1])
                    bits[:] = [None]*2

            except Exception as e:
                _LOGGER.error("exception %s: got bad data? index=%s, data=%s" % (e, value.index, value.data))

