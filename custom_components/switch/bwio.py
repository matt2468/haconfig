"""
Get digital switch information from BWIO pins.
"""
import logging
import voluptuous as vol

import custom_components.bwio as bwio
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (CONF_PLATFORM, STATE_ON, STATE_OFF)
from homeassistant.components.switch import SwitchDevice

_LOGGER = logging.getLogger(__name__)

BWIO = 'bwio'
DEPENDENCIES = [BWIO]
CONF_PINS = 'pins'

PLATFORM_SCHEMA = vol.Schema ({
    vol.Required(CONF_PLATFORM): BWIO,
    vol.Required(CONF_PINS): vol.Schema({ cv.positive_int: cv.string })
})

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the BWIO switch """
    # Verify that the BWIO board is present
    if bwio.BOARD is None:
        _LOGGER.error("A connection has not been made to the BWIO board")
        return False

    switches = []
    for pin, name in config.get(CONF_PINS).items():
        switches.append(BWIOOutput(pin, name))
        bwio.BOARD.register_output(switches[-1])

    if len(switches) == 0:
        _LOGGER.error("There were no switches to setup!")
    else:
        add_devices(switches)


class BWIOOutput(SwitchDevice):
    """Representation of an BWIO Switch."""

    def __init__(self, pin, name):
        _LOGGER.debug("Create %s on output pin %d" % (name, pin))
        self._pin = pin
        self._name = name
        self._state = None

    def new_output_data(self, allpins):
        self._state = (allpins & (1<<self._pin)) != 0
        self.update_ha_state()

    def turn_on(self, **kwargs):
        bwio.BOARD.set_output(self._pin, 1)

    def turn_off(self, **kwargs):
        bwio.BOARD.set_output(self._pin, 0)

    def update(self):
        bwio.BOARD.ping_output()

    @property
    def should_poll(self) -> bool: return False
    @property
    def name(self): return self._name
    @property
    def is_on(self): return self._state

