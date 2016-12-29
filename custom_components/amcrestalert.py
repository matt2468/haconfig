from homeassistant.const import EVENT_HOMEASSISTANT_STOP

DOMAIN = 'amcrestalert'
REQUIREMENTS = ['twisted']
DEVICES = []

def setup(hass, config):
    """ Setup the smtp server reactor """
    def newmessage(**kwargs):
        for dev in DEVICES:
            dev.newalert(**kwargs)

    from custom_components.amcrestsmtpreactor import AmcrestSmtpReactor
    reactor = AmcrestSmtpReactor(2525, newmessage)  # Maybe add port option someday
    reactor.start()
    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, lambda e: reactor.stop)
    return True

