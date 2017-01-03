import logging
import voluptuous as vol

from homeassistant.const import CONF_PLATFORM
from homeassistant.components.binary_sensor import BinarySensorDevice
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)
DOMAIN = 'amcrestserver'
CONF_CAMERAS = 'cameras'
DEPENDENCIES = [DOMAIN]

PLATFORM_SCHEMA = vol.Schema ({
    vol.Required(CONF_PLATFORM): DOMAIN,
    vol.Required(CONF_CAMERAS): vol.Schema({ cv.string : cv.string }) 
})

def setup_platform(hass, config, add_devices, discovery_info=None):
    from custom_components.amcrestserver import CONNECTION
    sensors = list()
    for dev in config[CONF_CAMERAS].items():
        sensor = AmcrestMotion(dev[0], dev[1])
        CONNECTION.add_device(sensor)
        sensors.append(sensor)
    add_devices(sensors)

class AmcrestMotion(BinarySensorDevice):
    """ Binary sensor interface to an input pin """

    def __init__(self, addr, name):
        _LOGGER.debug("Create %s on addr %s" % (name, addr))
        self._addr = addr
        self._name = name
        self._state = 'off'
        self._attr = {}

    def new_data(self, data):
        self._state = data.pop('motion')
        self._attr = data.copy()
        _LOGGER.debug("updating {} to {}, {}".format(self._addr, self._state, self._attr))
        self.update_ha_state()
        
    @property
    def should_poll(self) -> bool: return False
    @property
    def sensor_class(self):        return 'motion'
    @property
    def name(self):                return self._name
    @property
    def is_on(self):               return self._state == 'on'
    @property
    def device_state_attributes(self): return self._attr


