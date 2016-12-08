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
DEPENDENCIES = ['zwave', 'usercode']
DOMAIN = 'locklogger'

USER_CODE_ENTERED        = 16
TOO_MANY_FAILED_ATTEMPTS = 96

def setup(hass, config):
    """ Start a simple decoder of old lock alarm signals """
    decoder = OldSchlageLockAlarmDecoder(hass)
    dispatcher.connect(decoder.valuechanged, ZWaveNetwork.SIGNAL_VALUE_CHANGED, weak=False)
    return True

class OldSchlageLockAlarmDecoder():
    """ We aren't storing any real state, just turning multiple zwave alarms into a user messages """
    """ We expect to get a type alarm, followed by a value alarm.  At that time, deocde and reset """

    def __init__(self, hass):
        self.receivedtype = dict() # nodeid -> alarmtype
        self.hass = hass

    def getcodename(self, node, index):
        """ Get the label used for the given index. """
        # TODO, is there a way to lookup entities without referencing their modules?  Would be nice.
        from custom_components.usercode import CODEGROUP
        for entry in CODEGROUP.entities.values():
            if entry._value.index == index and entry._value.node == node:
                return entry.codelabel
        return "unknown!"

    def lockactivity(self, node, atype, aval):
        """ We have decoded a report (via alarms) from old Schlage locks """
        if atype == USER_CODE_ENTERED:
            logbook.log_entry(self.hass, node.name, 'User entered code {}'.format(self.getcodename(node, aval)))

        elif atype == TOO_MANY_FAILED_ATTEMPTS:
            msg = 'Multiple invalid door codes entered at {}'.format(node.name)
            persistent_notification.create(self.hass, msg, 'Potential Prowler')
            _LOGGER.warning(msg)

        else:
            _LOGGER.warning("Unknown lock alarm type! Investigate ({}, {}, {})".format(node.node_id, atype, aval))

    def valuechanged(self, value):
        """ We look for usercode and alarm messages from our locks here """
        if value.node.generic != zconst.GENERIC_TYPE_ENTRY_CONTROL or value.command_class != zconst.COMMAND_CLASS_ALARM:
            return

        _LOGGER.debug("alarm piece {} {} on {}".format(value.index, value.data, value.parent_id))

        if value.index == 0: # type
            self.receivedtype[value.parent_id] = value.data

        elif value.index == 1: # info, pop out our type and process
            if value.parent_id in self.receivedtype:
                self.lockactivity(value.node, self.receivedtype.pop(value.parent_id), value.data)
            else:
                _LOGGER.error("got alarm value {} from {} without type".format(value.data, value.parent_id))

