"""
Get digital input information from BWIO pins.
"""
import logging
import voluptuous as vol

import custom_components.bwio as bwio
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (CONF_PLATFORM, CONF_NAME, STATE_ON, STATE_OFF)
from homeassistant.components.binary_sensor import BinarySensorDevice, SENSOR_CLASSES


_LOGGER = logging.getLogger(__name__)

BWIO = 'bwio'
DEPENDENCIES = [BWIO]
CONF_PINS = 'pins'

PLATFORM_SCHEMA = vol.Schema ({
    vol.Required(CONF_PLATFORM): BWIO,
    vol.Required(CONF_PINS): vol.Schema({
         cv.positive_int: [ cv.string ] })
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the BWIO binary input"""
    # Verify that the BWIO board is present
    if bwio.BOARD is None:
        _LOGGER.error("A connection has not been made to the BWIO board")
        return False

    sensors = []
    for pin, (name, sensortype) in config.get(CONF_PINS).items():
        if sensortype not in SENSOR_CLASSES:
            _LOGGER.warning("Unable to setup %d:%s as %s is not a sensor type" % (pin, name, sensortype))
        sensors.append(BWIOInput(pin, name, sensortype))
        bwio.BOARD.register_input(sensors[-1])

    if len(sensors) == 0:
        _LOGGER.error("There were no sensors to setup!")
    else:
       add_devices(sensors)


class BWIOInput(BinarySensorDevice):
    """Representation of an BWIO Sensor."""

    def __init__(self, pin, name, sensortype):
        _LOGGER.debug("Create %s on input pin %d, type %s" % (name, pin, sensortype))
        self._pin = pin
        self._name = name
        self._type = sensortype
        self._state = None

    def new_input_data(self, allpins):
        self._state = (allpins & (1<<self._pin)) != 0
        self.update_ha_state()

    def update(self):
        bwio.BOARD.ping_input()

    @property
    def should_poll(self) -> bool: return False
    @property
    def sensor_class(self): return self._type
    @property
    def name(self): return self._name
    @property
    def is_on(self): return self._state


