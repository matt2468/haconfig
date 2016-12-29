import logging
import voluptuous as vol

from homeassistant.const import CONF_PLATFORM
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)
DOMAIN = 'amcrestalert'
DEPENDENCIES = ['amcrestalert']
PLATFORM_SCHEMA = vol.Schema ({
    vol.Required(CONF_PLATFORM): DOMAIN,
    vol.Required('cameras'): [ cv.string ]
})

def setup_platform(hass, config, add_devices, discovery_info=None):
    from custom_components.amcrestalert import DEVICES
    for host in config['cameras']:
        DEVICES.append(AmcrestAlert(host))
    add_devices(DEVICES)

class AmcrestAlert(Entity):
    """ Sensor interface for alert emails from an Amcrest camera """
    def __init__(self, host):
        self._host = host
        self._name = "Amcrest-{}".format(host)
        self._state = None

    def newalert(self, **kwargs):
        if self._host == kwargs.get('addr', None):
            _LOGGER.debug("updating {} with {}".format(self._host, kwargs))
            self._state = kwargs.get('event', b'').decode('utf_8')
            self.update_ha_state()

    @property
    def should_poll(self) -> bool: return False
    @property
    def name(self):                return self._name
    @property
    def state(self):               return self._state

