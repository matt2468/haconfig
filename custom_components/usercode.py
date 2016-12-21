"""
    Group all the locks info together so we can set the same code on each lock.  The Schlage
    locks do not let you download the user codes though I really don't care to store them
    anyhow, I just want to assign a name to each entry location (a la Vera handling) so I can
    remember which ones to delete/reassign later.

    We also have to resort to ugliness to get the data about UserCode availability.

    Not sure what can be reused.
"""

import logging
import collections
import operator
from datetime import datetime, timedelta

import homeassistant.components.zwave.const as zconst
from homeassistant.const import STATE_UNKNOWN
from homeassistant.components import zwave
from homeassistant.components import recorder
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import track_time_change

from pydispatch import dispatcher
from openzwave.network import ZWaveNetwork

_LOGGER = logging.getLogger(__name__)
DEPENDENCIES = ['zwave', 'recorder']
DOMAIN = 'usercode'

USER_CODE_STATUS_BYTE    = 8
NOT_USER_CODE_INDEXES    = (0, 254, 255)  # Enrollment code, refresh and code count
STATE_UNASSIGNED         = "unassigned"

CODEGROUP = None

def setup(hass, config):
    """ Set up our service call interface, a refresher task that stops itself and hook into the zwave events """
    global CODEGROUP

    hass.services.register(DOMAIN, "setusercode", set_user_code,
                { 'description': "Sets a user code on all locks",
                       'fields': { 'newname': {'description': 'A name for reference'},
                                      'code': {'description': 'The code to use as an ascii string of [0-9]'}}})
    hass.services.register(DOMAIN, "clearusercode", clear_user_code,
                { 'description': "Clear a user code on all locks using name",
                       'fields': { 'oldname': {'description': 'The name of the code'}}})
    hass.services.register(DOMAIN, "renameusercode", rename_user_code,
                { 'description': "Rename a user code on all locks",
                       'fields': { 'oldname': {'description': 'The present name for the code'},
                                   'newname': {'description': 'The new name for the code'}}})

    # when a new user code value is discovered, create a ZWaveUserCode and add to our list
    def valueadded(node, value):
        """ New ZWave Value added (generally on network start), make note of any user code entries on generic locks """
        if (node.generic == zconst.GENERIC_TYPE_ENTRY_CONTROL and     # node is generic lock
            value.command_class == zconst.COMMAND_CLASS_USER_CODE and # command class is user code
            value.index not in NOT_USER_CODE_INDEXES):                # real user code, not other indexes

            _LOGGER.debug("registered user code location {}, {} on {}".format(value.index, value.label, value.parent_id))
            CODEGROUP.add_entities([ZWaveUserCode(value)]) 

    def refresh_unknown(now):
        """
            We need to query ZWave UserCode values that we don't have any previous state for to see if they
            are available or occupied.  Using OZW Option RefreshAllUserCodes doesn't always work for me.
        """
        for code in CODEGROUP.entities.values():
            if code.state == STATE_UNKNOWN: 
                # Make a single request now, don't spam zwave network
                code.refresh()
                return
        # Everything has a status, stop the listener
        CODEGROUP.stoprefresher()

    def start_refresher(event):
        """ Don't start the refresher until the zwave network is ready to go """
        CODEGROUP.stoprefresher = track_time_change(hass, refresh_unknown, second=[0,15,30,45])

    # Connect up to the zwave network
    CODEGROUP = EntityComponent(_LOGGER, DOMAIN, hass)
    dispatcher.connect(valueadded, ZWaveNetwork.SIGNAL_VALUE_ADDED, weak=False)
    hass.bus.listen_once(zconst.EVENT_NETWORK_COMPLETE, start_refresher)
    return True


def set_user_code(service):
    """ Set the ascii number string code to index X on each selected lock """
    newname = service.data.get('newname')
    code = service.data.get('code')
    locksfound = set()
    locksused = set()

    if not all([ord(x) in range(0x30, 0x39) for x in code]):
        _LOGGER.error("Invalid code provided to setcode ({})".format(code))
        return

    # Assign to one free space on each lock
    for entry in sorted(CODEGROUP.entities.values(), key=operator.attrgetter('ordering')):
        locksfound.add(entry.lockid)
        if entry.lockid not in locksused and not entry.inuse:
            entry.set_code(newname, code)
            locksused.add(entry.lockid)

    locksskipped = locksfound - locksused
    if len(locksskipped) > 0:
        _LOGGER.error("Failed to set the code on the following locks {}".format(locksskipped))


def clear_user_code(service):
    """ Clear a code on each lock based on name """
    oldname = service.data.get('oldname')
    _LOGGER.debug("clear code {}".format(CODEGROUP.entities))
    for entry in CODEGROUP.entities.values():
        if entry.codelabel == oldname:
            entry.clear_code()


def rename_user_code(service):
    """ Rename a code whereever we find it """
    oldname = service.data.get('oldname')
    newname = service.data.get('newname')
    _LOGGER.debug("rename {} to {}".format(oldname, newname))
    for entry in CODEGROUP.entities.values():
        if entry.codelabel == oldname:
            entry.codelabel = newname
            entry.update_ha_state()


def hack_load_previous_state(entity_id):
    """ Hack to lookup the previous state if we can """
    try:
        from sqlalchemy import desc
        recorder._verify_instance()
        local = recorder._INSTANCE.engine.connect() # trying to avoid thread access issues I was having, this is a hack already, so...
        ret = local.execute("select state from states where domain='usercode' and entity_id=:eid order by state_id desc",
                                {'eid': entity_id}).first()[0]
        local.close()
        return ret
    except Exception as e:
        _LOGGER.debug("Failed to load previous states: {}".format(e))
        return STATE_UNKNOWN



class ZWaveUserCode(zwave.ZWaveDeviceEntity, Entity):
    """ Represents a single user code entry value on a z-wave node. """
    """ Our state is the label assigned to the user code or unassigned if nothing is there """

    def __init__(self, value):
        zwave.ZWaveDeviceEntity.__init__(self, value, 'usercode')
        self.codelabel = hack_load_previous_state(self.entity_id)
        _LOGGER.debug("ZWaveUserCode initial state {}".format(self.codelabel))
        dispatcher.connect(self._value_changed, ZWaveNetwork.SIGNAL_VALUE_CHANGED)

    def _value_changed(self, value):
        """ We got a code update, data is probably just '****' but there is a status byte in the command class """
        if self._value.value_id == value.value_id:
            # PyOZW doesn't expose command class data, we reach into the raw message data and get it ourselves
            assigned = bool(value.network.manager.getNodeStatistics(value.home_id, value.parent_id)['lastReceivedMessage'][USER_CODE_STATUS_BYTE])
            _LOGGER.debug("{} code {} assigned {}".format(value.parent_id, value.index, assigned))
            # Update our label if necessary (don't have one or its no longer set on the lock)
            if not assigned:
                self.codelabel = STATE_UNASSIGNED
            elif self.codelabel == STATE_UNKNOWN:
                self.codelabel = "Unnamed Entry {}".format(value.index) # we didn't load a previous state
            self.update_ha_state()

    def refresh(self):
        """ Only called if for some reason, we never got an initial status report from this value """
        _LOGGER.debug("refreshing data at {}".format(self._value.index))
        self._value.refresh()

    def set_code(self, label, code):
        """ Set the code at this objects index/location """
        _LOGGER.debug("setting code at {} with label {}".format(self._value.index, label))
        self.codelabel = label
        self._value.data = code
        # Setting data will cause a value change and subsequent state update call

    def clear_code(self):
        """ Clear the code at this objects index/location """
        _LOGGER.debug("clearing code at {} with label {}".format(self._value.index, self.codelabel))
        self._value.data = "\0\0\0\0"  # My patch to OZW should cause a clear
        # don't clear label until we get confirmation from the lock

    """
      Code Properties:
        ordering: a value by which to order user codes when picking an empty spot
        lockid:   a unique identifier for the lock this code is bound to
        inuse:    true if we can't assign codes to it at this time
      Overriden Properties:
        hidden:   true as the custom panel takes care of things now
        state:    one of unknown, unassigned or the name label assigned
    """
    @property
    def ordering(self) -> int: return self._value.index
    @property
    def lockid(self) -> str:   return self._value.parent_id # NOTE: this is a zwave id, not a HA entity id
    @property
    def inuse(self) -> bool:   return self.codelabel != STATE_UNASSIGNED
    @property
    def hidden(self) -> bool:  return True
    @property
    def state(self) -> str:    return self.codelabel

    @property
    def device_state_attributes(self):
        """ Append some more interesting attributes to the state info """
        data = super().device_state_attributes
        data['inuse'] = self.inuse
        data['index'] = self._value.index
        return data

