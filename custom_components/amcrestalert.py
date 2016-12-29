from homeassistant.const import EVENT_HOMEASSISTANT_STOP, EVENT_TIME_CHANGED

DOMAIN = 'amcrestalert'
REQUIREMENTS = ['twisted']
DEVICES = []

def setup(hass, config):
    """ Setup the smtp server reactor """
    def newmessage(**kwargs):
        for dev in DEVICES:
            dev.newalert(**kwargs)

    def periodic(event):
        for dev in DEVICES:
            dev.periodic()

    from custom_components.amcrestsmtpreactor import AmcrestSmtpReactor
    reactor = AmcrestSmtpReactor(2525, newmessage)  # Maybe add port option someday
    reactor.start()
    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, lambda e: reactor.stop)
    hass.bus.listen(EVENT_TIME_CHANGED, periodic)
    return True

