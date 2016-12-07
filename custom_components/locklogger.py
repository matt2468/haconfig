"""
    I think this  use of alarms is entirely specific to these old locks, there appears to be an actual
    lock logging class for newer zwave devices.  Ah, corner cases, my old friend. The default HA ZWaveAlarmSensor
    treats zwave alarms as separate state values and therefore won't send updates if the same door code entered
    multiple times in succession, hence the zwave value change decoding below.
"""

import logging
from pydispatch import dispatcher
from openzwave.network import ZWaveNetwork

import homeassistant.components.zwave.const as zconst
from homeassistant.components import zwave, logbook, persistent_notification

_LOGGER = logging.getLogger(__name__)
DEPENDENCIES = ['zwave']
DOMAIN = 'locklogger'

USER_CODE_ENTERED        = 16
TOO_MANY_FAILED_ATTEMPTS = 96

def setup(hass, config):
    """ Start a simple decoder of old lock alarm signals """
    decoder = OldSchlageLockAlarmDecoder(hass)
    dispatcher.connect(decoder.valuechanged, ZWaveNetwork.SIGNAL_VALUE_CHANGED, weak=False)
    return True

class OldSchlageLockAlarmDecoder():
    """ We aren't storing any state, just turning multiple zwave alarms into a user messages """
    """ We expect to get a type alarm, followed by a value alarm.  At that time, deocde and reset """

    def __init__(self, hass):
        self.receivedtype = dict() # nodeid -> alarmtype
        self.hass = hass

    def getlockname(self, nodeid):
        """ TODO get the lock name somehow """
        return "TODO/{}".format(nodeid)

    def getusername(self, index):
        """ TODO get the user name somehow """
        return "TODO/{}".format(index)


    def lockactivity(self, nodeid, atype, aval):
        """ We have decoded a report (via alarms) from old Schlage locks """
        if atype == USER_CODE_ENTERED:
            logbook.log_entry(self.hass, self.getlockname(nodeid), 'User entered code {}'.format(self.getusername(aval)))

        elif atype == TOO_MANY_FAILED_ATTEMPTS:
            msg = 'Multiple invalid door codes enetered at {}'.format(self.getlockname(nodeid))
            persistent_notification.create(self.hass, msg, 'Potential Prowler')
            _LOGGER.warning(msg)

        else:
            _LOGGER.warning("Unknown lock alarm type! Investigate ({}, {}, {})".format(nodeid, atype, aval))

    def valuechanged(self, value):
        """ We look for usercode and alarm messages from our locks here """
        if value.node.generic != zconst.GENERIC_TYPE_ENTRY_CONTROL or value.command_class != zconst.COMMAND_CLASS_ALARM:
            return

        _LOGGER.debug("alarm piece {} {} on {}".format(value.index, value.data, value.parent_id))

        if value.index == 0: # type
            self.receivedtype[value.parent_id] = value.data

        elif value.index == 1: # info, pop out our type and process
            if value.parent_id in self.receivedtype:
                self.lockactivity(value.parent_id, self.receivedtype.pop(value.parent_id), value.data)
            else:
                _LOGGER.error("got alarm value {} from {} without type".format(value.data, value.parent_id))

