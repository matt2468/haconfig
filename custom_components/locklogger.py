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
DOMAIN = 'security'

USER_CODE_ENTERED        = 16
TOO_MANY_FAILED_ATTEMPTS = 96
EVENT_DOOR_CODE_ENTERED       = 'security.doorcodeentered'
EVENT_DOOR_TOO_MANY_ATTEMPTS  = 'security.toomanydoorattempts'


def setup(hass, config):
    """ Start a simple decoder of old lock alarm signals """
    decoder = LockAlarmDecoder(hass)
    dispatcher.connect(decoder.valuechanged, ZWaveNetwork.SIGNAL_VALUE_CHANGED, weak=False)
    return True


class LockAlarmDecoder():
    """ We aren't storing any real state, just turning multiple zwave alarms into a user messages """
    """ We expect to get a type alarm, followed by a value alarm.  At that time, deocde and reset """

    def __init__(self, hass):
        self.receivedtype = dict() # nodeid -> alarmtype
        self.hass = hass

    def getcodename(self, node, index):
        """ Get the label used for the given index or get return the nodeid/index """
        # TODO, is there a way to lookup other entities without referencing their modules?  Would be nice.
        from custom_components.usercode import CODEGROUP
        for entry in CODEGROUP.entities.values():
            if entry._value.index == index and entry._value.node == node:
                return entry.codelabel
        return "{}/{}".format(node.node_id, index)

    def lockactivity(self, node, atype, aval):
        """ We have decoded a report (via alarms) from old Schlage locks """
        if atype == USER_CODE_ENTERED:
            codename = self.getcodename(node, aval)
            self.hass.bus.fire(EVENT_DOOR_CODE_ENTERED, {'node':node.name, 'name':codename})
            logbook.log_entry(self.hass, node.name, 'User entered code {}'.format(codename))

        elif atype == TOO_MANY_FAILED_ATTEMPTS:
            self.hass.bus.fire(EVENT_DOOR_TOO_MANY_ATTEMPTS, {'node':node.name})
            msg = 'Multiple invalid door codes entered at {}'.format(node.name)
            persistent_notification.create(self.hass, msg, 'Potential Prowler')
            _LOGGER.warning(msg)

        else:
            _LOGGER.warning("Unknown lock alarm type! Investigate ({}, {}, {})".format(node.node_id, atype, aval))

    def valuechanged(self, value):
        """ Switch on (manufacturer_id, product_type, product_id) to determine what method to use """
        mid = int(value.node.manufacturer_id, 16)
        pid = (int(value.node.product_type, 16), int(value.node.product_id, 16))

        if mid == 0x003b: # Schlage
            if pid == (0x634b, 0x5044): # BE-369
                self.decodebe369(value)

    def decodebe369(self, value):
        """ We look for usercode and alarm messages from our known locks here """
        if value.node.generic != zconst.GENERIC_TYPE_ENTRY_CONTROL: return
        if value.command_class != zconst.COMMAND_CLASS_ALARM:       return

        _LOGGER.debug("be369 piece {} {} on {}".format(value.index, value.data, value.parent_id))

        if value.index == 0: # type
            self.receivedtype[value.parent_id] = value.data

        elif value.index == 1: # info, pop out our type and process
            if value.parent_id in self.receivedtype:
                self.lockactivity(value.node, self.receivedtype.pop(value.parent_id), value.data)
            else:
                _LOGGER.error("got alarm value {} from {} without type".format(value.data, value.parent_id))

