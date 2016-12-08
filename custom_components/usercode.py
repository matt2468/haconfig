"""
    Group all the locks info together so we can set the same code in the same slot on each lock.  The Schlage
    locks do not let you download the user codes though I really don't care to store them anyhow, I just want
    to assign a name to each entry location (a la Vera handling) so I can remember which ones to delete/reassign
    later.

    We also have to resort to ugliness to get the data about UserCode availability.

    Not sure what can be reused.
"""

import logging
import collections
import operator

import homeassistant.components.zwave.const as zconst
from homeassistant.const import STATE_UNKNOWN
from homeassistant.components import zwave
from homeassistant.components import recorder
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.util.yaml  import load_yaml, dump

from pydispatch import dispatcher
from openzwave.network import ZWaveNetwork

_LOGGER = logging.getLogger(__name__)
DEPENDENCIES = ['zwave', 'recorder']
DOMAIN = 'usercode'
PERSIST_FILE = 'lockinfo.yaml'

USER_CODE_STATUS_BYTE    = 8
NOT_USER_CODE_INDEXES    = (0, 254, 255)  # Enrollment code, refresh and code count
STATE_UNASSIGNED         = "unassigned"

CODEGROUP = None

def setup(hass, config):
    """ Thanks to pydispatcher being globally available in the application, we can hook into zwave here """
    global CODEGROUP

    hass.services.register(DOMAIN, "setusercode", set_user_code,
                { 'description': "Sets a user code on all locks",
                       'fields': { 'name': {'description': 'A name for reference'},
                                   'code': {'description': 'The number code to use as an ascii string'}}})
    hass.services.register(DOMAIN, "clearusercode", clear_user_code,
                { 'description': "Clear a user code on all locks using name or index (only provide one of name/index)",
                       'fields': { 'name': {'description': 'The name for the code'}}})

    # when a new user code value is discovered, create a ZWaveUserCode and add to our list
    def valueadded(node, value):
        """ New ZWave Value added (generally on network start), make note of any user code entries on generic locks """
        if (node.generic == zconst.GENERIC_TYPE_ENTRY_CONTROL and     # node is generic lock
            value.command_class == zconst.COMMAND_CLASS_USER_CODE and # command class is user code
            value.index not in NOT_USER_CODE_INDEXES):                # real user code, not other indexes

            _LOGGER.debug("registered user code location {}, {} on {}".format(value.index, value.label, value.parent_id))
            CODEGROUP.add_entities([ZWaveUserCode(value)]) 

    # Connect up to the zwave network
    CODEGROUP = EntityComponent(_LOGGER, DOMAIN, hass)
    dispatcher.connect(valueadded, ZWaveNetwork.SIGNAL_VALUE_ADDED, weak=False)
    return True


def set_user_code(service):
    """ Set the ascii number string code to index X on each selected lock """
    name = service.data.get('name')
    code = service.data.get('code')
    locksfound = set()
    locksused = set()

    if not all([ord(x) in range(0x30, 0x39) for x in code]):
        _LOGGER.error("Invalid code provided to setcode ({})".format(code))
        return

    # Assign to one free space on each lock
    for entry in sorted(CODEGROUP.entities.values(), key=operator.attrgetter('ordering')):
        locksfound.add(entry.lockentity)
        if entry.lockentity not in locksused and not entry.inuse:
            entry.set_code(name, code)
            locksused.add(entry.lockentity)

    locksskipped = locksfound - locksused
    if len(locksskipped) > 0:
        _LOGGER.error("Failed to set the code on the following locks {}".format(locksskipped))


def clear_user_code(service):
    """ Clear a code on each lock based on name """
    name = service.data.get('name')
    _LOGGER.debug("clear code {}".format(CODEGROUP.entities))
    for entry in CODEGROUP.entities.values():
        _LOGGER.debug("Compare {} to {}".format(entry.codelabel, name))
        if entry.codelabel == name:
            entry.clear_code()


def hack_load_previous_state(entity_id):
    """ Hack to lookup the previous state if we can """
    try:
        from sqlalchemy import desc
        local = recorder._INSTANCE.engine.connect() # trying to avoid thread access issues I was having
        ret = local.execute("select state from states where domain='usercode' and entity_id=:eid order by state_id desc",
                                {'eid': entity_id}).first()[0]
        local.close()
        return ret
    except Exception as e:
        _LOGGER.debug("Failed to load previous states: {}".format(e))
        return STATE_UNKNOWN



class ZWaveUserCode(zwave.ZWaveDeviceEntity, Entity):  # TODO: maybe create a generic HA component like UserCode
    """ Schlage locks don't send you the code, but they do tell if the spot is has a code assigned """
    """ Our state is the label assigned to the user code or unassigned if nothing is there """

    def __init__(self, value):
        zwave.ZWaveDeviceEntity.__init__(self, value, 'usercode')
        dispatcher.connect(self._value_changed, ZWaveNetwork.SIGNAL_VALUE_CHANGED)
        self.codelabel = hack_load_previous_state(self.entity_id)
        _LOGGER.debug("ZWaveUserCode initial state {}".format(self.codelabel))

    def _value_changed(self, value):
        """ We got a code update, data is just '****' but there is a status byte in the command class """
        if self._value.value_id == value.value_id:
            # PyOZW doesn't expose command class data, we reach into the raw message data and get it ourselves
            assigned = bool(value.network.manager.getNodeStatistics(value.home_id, value.parent_id)['lastReceivedMessage'][USER_CODE_STATUS_BYTE])
            _LOGGER.debug("{} code {} assigned {}".format(value.parent_id, value.index, assigned))
            # Update our label
            if not assigned:
                self.codelabel = STATE_UNASSIGNED
            elif self.codelabel == STATE_UNKNOWN:
                self.codelabel = "Unnamed Entry {}".format(value.index) # we didn't load a previous state
            self.update_ha_state()

    def set_code(self, label, code):
        _LOGGER.debug("setting code with label {}".format(label))
        self.codelabel = label
        self._value.data = code

    def clear_code(self):
        _LOGGER.debug("setting code with label {}".format(self.codelabel))
        self._value.data = "\0\0\0\0"  # My patch to OZW should cause a clear
        # don't clear label until we get confirmation from the lock

    """
      Properties:
        orderby:    a value by which to order user codes (like index)
        lockentity: the entity_id of the lock this code is bound to
        hidden:     true for unknown and unassigned codes
        inuse:      true if we can't assign codes to it at this time
        state:      one of unknown, unassigned or the name label assigned to it
    """
    @property
    def ordering(self) -> int:   return self._value.index
    @property
    def lockentity(self) -> str: return self._value.parent_id # TODO, this is a zwave id, not an entity id
    @property
    def hidden(self) -> bool:    return self.codelabel in (STATE_UNKNOWN, STATE_UNASSIGNED)
    @property
    def inuse(self) -> bool:     return self.codelabel != STATE_UNASSIGNED
    @property
    def state(self) -> str:      return self.codelabel

