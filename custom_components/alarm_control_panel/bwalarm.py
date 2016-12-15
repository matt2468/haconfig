"""
 My take on the manual alarm control panel
"""
import datetime
import logging
import re
import voluptuous as vol
from operator import attrgetter

from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY, STATE_ALARM_ARMED_HOME, STATE_ALARM_DISARMED,
    STATE_ALARM_PENDING, STATE_ALARM_TRIGGERED, CONF_PLATFORM, CONF_NAME,
    CONF_CODE, CONF_PENDING_TIME, CONF_TRIGGER_TIME, CONF_DISARM_AFTER_TRIGGER,
    EVENT_STATE_CHANGED, EVENT_TIME_CHANGED, STATE_ON)
import homeassistant.components.alarm_control_panel as alarm
import homeassistant.helpers.config_validation as cv
from homeassistant.util.dt import utcnow as now
from homeassistant.helpers.event import async_track_point_in_time

CONF_HEADSUP   = 'headsup'
CONF_IMMEDIATE = 'immediate'
CONF_DELAYED   = 'delayed'
CONF_NOTATHOME = 'notathome'
CONF_ALARM     = 'alarm'

PLATFORM_SCHEMA = vol.Schema({
    vol.Required(CONF_PLATFORM):  'bwalarm',
    vol.Required(CONF_NAME):      cv.string,
    vol.Required(CONF_PENDING_TIME): vol.All(vol.Coerce(int), vol.Range(min=0)),
    vol.Required(CONF_TRIGGER_TIME): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional(CONF_HEADSUP):   cv.entity_ids, # things to show as a headsup at top of GUI
    vol.Optional(CONF_IMMEDIATE): cv.entity_ids, # things that cause an immediate alarm
    vol.Optional(CONF_DELAYED):   cv.entity_ids, # things that allow a delay before alarm
    vol.Optional(CONF_NOTATHOME): cv.entity_ids, # things that we ignore when at home
    vol.Optional(CONF_ALARM):     cv.entity_ids  # switches to set when alarming
})

_LOGGER = logging.getLogger(__name__)

def setup_platform(hass, config, add_devices, discovery_info=None):
    alarm = BWAlarm(hass, config)
    hass.bus.async_listen(EVENT_STATE_CHANGED, alarm.state_change_listener)
    add_devices([alarm])

class AlarmState(object):
    """ Wrap alarm state, signals and time in one object, can create in future """
    def __init__(self, label, immediate, delayed, ignored, howlong = None):
        self.label = label
        self.immediate = immediate  # Immediate alarm
        self.delayed = delayed      # Delayed alarm pending disarm
        self.ignored = ignored      # Ignored for whatever reason (at home, left open, etc)
        self.when = now()
        if howlong is not None: 
            self.when += howlong
    def __repr__(self):
        return "{}@{} (IMMED: {}, DELAY: {}, IGNORE: {})".format(self.label, self.when, self.immediate, self.delayed, self.ignored)


class BWAlarm(alarm.AlarmControlPanel):
    """ My alarm 'owns' the provided sensors """

    def __init__(self, hass, config):
        """ Initalize the manual alarm panel """
        self._hass = hass
        self._name = config[CONF_NAME]
        self._immediate = config.get(CONF_IMMEDIATE, [])
        self._delayed   = config.get(CONF_DELAYED, [])
        self._notathome = config.get(CONF_NOTATHOME, [])
        self._alarms    = config.get(CONF_ALARM, [])
        self._headsup   = config.get(CONF_HEADSUP, [])
        self._allinputs = set(self._immediate) | set(self._delayed) | set(self._notathome)
        self._pending_time = datetime.timedelta(seconds=config[CONF_PENDING_TIME])
        self._trigger_time = datetime.timedelta(seconds=config[CONF_TRIGGER_TIME])
        self._lasttrigger  = ""

        self._state = [AlarmState(STATE_ALARM_DISARMED, set(), set(), self._allinputs)]
    ### Alarm properties

    @property
    def should_poll(self) -> bool:
        return False
    @property
    def name(self) -> str:
        return self._name
    @property
    def changed_by(self) -> str:
        return self._lasttrigger
    @property
    def device_state_attributes(self):
        state = self.currently()
        return {
            'immediate': sorted(list(state.immediate)),
            'delayed':   sorted(list(state.delayed)),
            'ignored':   sorted(list(state.ignored)),
            'headsup':   sorted(list(self._headsup)),
            'changedby': self.changed_by
        }

    @property
    def state(self):
        """Return the state of the device."""
        _LOGGER.debug("STATE IN {}".format(self._state))
        current = self.currently()
        if len(self._state) > 1: # Tell HA to notice us later in time, as there is more to come
            async_track_point_in_time(self._hass, self.async_update_ha_state, self._state[1].when)
        _LOGGER.debug("STATE OUT {}".format(self._state))
        return current.label


    def currently(self):
        """ Pop off dead state and return the current object """
        currently = now()
        while len(self._state) > 1 and self._state[1].when < currently: 
            del self._state[0]
        return self._state[0]

    def noton(self, eid):
        """ For filtering out sensors already tripped """
        return not self._hass.states.is_state(eid, STATE_ON)

    def getsignals(self):
        """ Figure out what to sense and how, returns a tuple of sets """
        i = set(filter(self.noton, self._immediate))
        d = set(filter(self.noton, self._delayed))
        x = self._allinputs - (i | d)
        return (i, d, x)

    ### Actions from the outside world that affect us

    def state_change_listener(self, event):
        """ Something changed, we only care about things turning on at this point """
        new = event.data['new_state']
        if new is None or new.state != STATE_ON:
            return

        state = self.currently()
        eid = event.data['entity_id']
        if eid in state.immediate:
            _LOGGER.debug("Immediate alarm on {}".format(eid))
            self._lasttrigger = eid
        elif eid in state.delayed:
            _LOGGER.debug("Delayed alarm on {}".format(eid))
            self._lasttrigger = eid


    def alarm_disarm(self, code=None):
        """ We are disarmed at this point, clears any other future state """
        self._state = [AlarmState(STATE_ALARM_DISARMED, set(), set(), self._allinputs)]
        self.update_ha_state()

    def alarm_arm_home(self, code=None):
        """ We are armed home at this point, clears any other future state """
        sigs = self.getsignals()
        self._state = [AlarmState(STATE_ALARM_ARMED_HOME, *sigs)]
        self.update_ha_state()

    def alarm_arm_away(self, code=None):
        """ We are pending now, to be armed away after that, clears any other future state """
        sigs = self.getsignals()
        self._state = [AlarmState(STATE_ALARM_PENDING, *sigs), AlarmState(STATE_ALARM_ARMED_AWAY, *sigs, howlong=self._pending_time)]
        self.update_ha_state()

    def alarm_trigger(self, code=None):
        """ Trigger the alarm now, insert into current events, return to orig state and sort """
        current = self.state
        self._state.extend([AlarmState(STATE_ALARM_TRIGGERED), AlarmState(current, self._trigger_time)])
        self._state.sort(key=attrgetter('when'))
        self.update_ha_state()

