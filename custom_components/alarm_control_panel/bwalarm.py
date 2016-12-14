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
    EVENT_STATE_CHANGED, EVENT_TIME_CHANGED)
import homeassistant.components.alarm_control_panel as alarm
import homeassistant.helpers.config_validation as cv
from homeassistant.util.dt import utcnow as now
from homeassistant.helpers.event import async_track_point_in_time

CONF_IMMEDIATE = 'immediate'
CONF_DELAYED   = 'delayed'
CONF_NOTATHOME = 'notathome'
CONF_ALARM     = 'alarm'

PLATFORM_SCHEMA = vol.Schema({
    vol.Required(CONF_PLATFORM):  'bwalarm',
    vol.Required(CONF_NAME):      cv.string,
    vol.Required(CONF_PENDING_TIME): vol.All(vol.Coerce(int), vol.Range(min=0)),
    vol.Required(CONF_TRIGGER_TIME): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional(CONF_IMMEDIATE): cv.entity_ids,  # things that cause an immediate alarm
    vol.Optional(CONF_DELAYED):   cv.entity_ids,  # things that allow a delay before alarm
    vol.Optional(CONF_NOTATHOME): cv.entity_ids,  # things that we ignore when at home
    vol.Optional(CONF_ALARM):     cv.entity_ids   # switches to set when alarming
})

_LOGGER = logging.getLogger(__name__)

def setup_platform(hass, config, add_devices, discovery_info=None):
    alarm = BWAlarm(hass, config)
    hass.bus.async_listen(EVENT_STATE_CHANGED, alarm.state_change_listener)
    add_devices([alarm])


class AlarmState(object):
    """ Wrap alarm state/time in one object, can create in future """
    def __init__(self, label, howlong = None):
        self.label = label
        self.when = now()
        if howlong is not None: 
            self.when += howlong
    def __repr__(self):
        return "{}@{}".format(self.label, self.when)


class BWAlarm(alarm.AlarmControlPanel):
    """ My alarm 'owns' the provided sensors """

    def __init__(self, hass, config):
        """ Initalize the manual alarm panel """
        self._state = [AlarmState(STATE_ALARM_DISARMED)]
        self._hass = hass
        self._name = config[CONF_NAME]
        self._pending_time = datetime.timedelta(seconds=config[CONF_PENDING_TIME])
        self._trigger_time = datetime.timedelta(seconds=config[CONF_TRIGGER_TIME])
        self._lasttrigger = "yourmomma"
        self._listento = set()
        for k in (CONF_IMMEDIATE, CONF_DELAYED, CONF_NOTATHOME):
            self._listento.update(config.get(k, []))

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
        data = {}
        data['listento'] = sorted(list(self._listento))
        return data

    @property
    def state(self):
        """Return the state of the device."""
        _LOGGER.debug("STATE IN {}".format(self._state))
        # Pop off dead state
        currently = now()
        while len(self._state) > 1 and self._state[1].when < currently: 
            del self._state[0]

        if len(self._state) > 1: # Tell HA to notice us later in time
            async_track_point_in_time(self._hass, self.async_update_ha_state, self._state[1].when)
        _LOGGER.debug("STATE OUT {}".format(self._state))
        return self._state[0].label


    ### Actions from the outside world that affect us

    def state_change_listener(self, event):
        if event.data['entity_id'] in self._listento:
            _LOGGER.debug("Alarm hears: {}".format(event))
            #self._lasttrigger = asdfasdf

    def alarm_disarm(self, code=None):
        """ We are disarmed at this point, clears any other future state """
        self._state = [AlarmState(STATE_ALARM_DISARMED)]
        self.update_ha_state()

    def alarm_arm_home(self, code=None):
        """ We are armed home at this point, clears any other future state """
        self._state = [AlarmState(STATE_ALARM_ARMED_HOME)]
        self.update_ha_state()

    def alarm_arm_away(self, code=None):
        """ We are pending now, to be armed away after that, clears any other future state """
        self._state = [AlarmState(STATE_ALARM_PENDING), AlarmState(STATE_ALARM_ARMED_AWAY, self._pending_time)]
        self.update_ha_state()

    def alarm_trigger(self, code=None):
        """ Trigger the alarm now, insert into current events, return to orig state and sort """
        current = self.state
        self._state.extend([AlarmState(STATE_ALARM_TRIGGERED), AlarmState(current, self._trigger_time)])
        self._state.sort(key=attrgetter('when'))
        self.update_ha_state()

