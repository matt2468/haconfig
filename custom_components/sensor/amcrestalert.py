import logging
import voluptuous as vol

from homeassistant.const import CONF_PLATFORM, CONF_HOST, CONF_NAME, STATE_OFF
from homeassistant.helpers.entity import Entity
from homeassistant.util.dt import now
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)
DOMAIN = 'amcrestalert'
DEPENDENCIES = ['amcrestalert']
PLATFORM_SCHEMA = vol.Schema ({
    vol.Required(CONF_PLATFORM): DOMAIN,
    vol.Required('cameras'): [ vol.Schema ({ 
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_NAME): cv.string,
     })]
})

def setup_platform(hass, config, add_devices, discovery_info=None):
    from custom_components.amcrestalert import DEVICES
    for cfg in config['cameras']:
        DEVICES.append(AmcrestAlert(cfg[CONF_HOST], cfg[CONF_NAME]))
    add_devices(DEVICES)

class AmcrestAlert(Entity):
    """ Sensor interface for alert emails from an Amcrest camera """
    def __init__(self, host, name):
        self._host  = host
        self._name  = name
        self._state = STATE_OFF
        self._ts    = now()

    def newalert(self, **kwargs):
        if self._host == kwargs.get('addr', None):
            _LOGGER.debug("updating {} with {}".format(self._host, kwargs))
            self._state = kwargs.get('event', b'').decode('utf_8')
            self._ts = now()
            self.update_ha_state()

    def periodic(self):
        """ We get alerts every 10 seconds, clear after 20 seconds of nothing """
        if self._state is not STATE_OFF:
            diff = now() - self._ts
            if diff.seconds > 20:
                self._state = STATE_OFF
                self.update_ha_state()

    @property
    def should_poll(self) -> bool: return False
    @property
    def name(self):                return self._name
    @property
    def state(self):               return self._state

