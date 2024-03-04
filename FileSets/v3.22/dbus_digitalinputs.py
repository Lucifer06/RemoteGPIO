#!/usr/bin/python3 -u

#### modified for ExtTransferSwitch package

import sys, os
import signal
from threading import Thread
from select import select, epoll, EPOLLPRI
from functools import partial
from collections import namedtuple
from argparse import ArgumentParser
import traceback
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))

from dbus.mainloop.glib import DBusGMainLoop
import dbus
from gi.repository import GLib
from vedbus import VeDbusService, VeDbusItemImport
from settingsdevice import SettingsDevice

VERSION = '0.23'
MAXCOUNT = 2**31-1
SAVEINTERVAL = 60000

INPUT_FUNCTION_COUNTER = 1
INPUT_FUNCTION_INPUT = 2

Translation = namedtuple('Translation', ['no', 'yes'])

# Only append at the end
INPUTTYPES = [
    'Disabled',
    'Pulse meter',
    'Door',
    'Bilge pump',
    'Bilge alarm',
    'Burglar alarm',
    'Smoke alarm',
    'Fire alarm',
    'CO2 alarm',
    'Generator',
    'Generic I/O',
    'Touch enable',
#### added for ExtTransferSwitch package -- must be LAST in the list
    'Transfer switch'
]

# Translations. The text will be used only for GetText, it will be translated
# in the gui.
TRANSLATIONS = [
    Translation('low', 'high'),
    Translation('off', 'on'),
    Translation('no', 'yes'),
    Translation('open', 'closed'),
    Translation('ok', 'alarm'),
    Translation('running', 'stopped'),
#### added for ExtTransferSwitch package
    Translation('on generator', 'on grid')
]

class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)

class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)

class BasePulseCounter(object):
    pass

class DebugPulseCounter(BasePulseCounter):
    def __init__(self):
        self.gpiomap = {}

    def register(self, path, gpio):
        self.gpiomap[gpio] = None
        return 0

    def unregister(self, gpio):
        del self.gpiomap[gpio]

    def registered(self, gpio):
        return gpio in self.gpiomap

    def __call__(self):
        from itertools import cycle
        from time import sleep
        for level in cycle([0, 1]):
            for gpio in list(self.gpiomap.keys()):
                yield gpio, level
                sleep(0.25/len(self.gpiomap))

class EpollPulseCounter(BasePulseCounter):
    def __init__(self):
        self.gpiomap = {}
        self.states = {}
        self.ob = epoll()

    def register(self, path, gpio):
        path = os.path.realpath(path)

        # Set up gpio for rising edge interrupts
        with open(os.path.join(path, 'edge'), 'ab') as fp:
            fp.write(b'both')

        fp = open(os.path.join(path, 'value'), 'rb')
        level = int(fp.read()) # flush it in case it's high at startup
        self.gpiomap[gpio] = fp
        self.states[gpio] = level
        self.ob.register(fp, EPOLLPRI)
        return level

    def unregister(self, gpio):
        fp = self.gpiomap[gpio]
        self.ob.unregister(fp)
        del self.gpiomap[gpio]
        del self.states[gpio]
        fp.close()

    def registered(self, gpio):
        return gpio in self.gpiomap

    def __call__(self):
        while True:
            # We have a timeout of 1 second on the poll, because poll() only
            # looks at files in the epoll object at the time poll() was called.
            # The timeout means we let other files (added via calls to
            # register/unregister) into the loop at least that often.
            self.ob.poll(1)

            # When coming out of the epoll call, we read all the gpios to make
            # sure we didn't miss any edges.  This is a safety fallback that
            # ensures everything is up to date once a second, but
            # edge-triggered results are handled immediately.
            # NOTE: There has not been a report of a missed interrupt yet.
            # Belts and suspenders.
            for gpio, fp in list(self.gpiomap.items()):
                os.lseek(fp.fileno(), 0, os.SEEK_SET)
                v = int(os.read(fp.fileno(), 1))
                if v != self.states[gpio]:
                    self.states[gpio] = v
                    yield gpio, v

class PollingPulseCounter(BasePulseCounter):
    def __init__(self):
        self.gpiomap = {}

    def register(self, path, gpio):
        path = os.path.realpath(path)

        fp = open(os.path.join(path, 'value'), 'rb')
        level = int(fp.read())
        self.gpiomap[gpio] = [fp, level]
        return level

    def unregister(self, gpio):
        del self.gpiomap[gpio]

    def registered(self, gpio):
        return gpio in self.gpiomap

    def __call__(self):
        from itertools import cycle
        from time import sleep
        while True:
            for gpio, (fp, level) in list(self.gpiomap.items()):
                fp.seek(0, os.SEEK_SET)
                v = int(fp.read())
                if v != level:
                    self.gpiomap[gpio][1] = v
                    yield gpio, v
            sleep(1)

class HandlerMaker(type):
    """ Meta-class for keeping track of all extended classes. """
    def __init__(cls, name, bases, attrs):
        if not hasattr(cls, 'handlers'):
            cls.handlers = {}
        else:
            cls.handlers[cls.type_id] = cls

class PinHandler(object, metaclass=HandlerMaker):
    product_id = 0xFFFF
    _product_name = 'Generic GPIO'
    dbus_name = "digital"
    def __init__(self, bus, base, path, gpio, settings):
        self.gpio = gpio
        self.path = path
        self.bus = bus
        self.settings = settings
        self._level = 0 # Remember last state

        self.service = VeDbusService(
            "{}.{}.input{:02d}".format(base, self.dbus_name, gpio), bus=bus)

        # Add objects required by ve-api
        self.service.add_path('/Mgmt/ProcessName', __file__)
        self.service.add_path('/Mgmt/ProcessVersion', VERSION)
        self.service.add_path('/Mgmt/Connection', path)
        self.service.add_path('/DeviceInstance', gpio)
        self.service.add_path('/ProductId', self.product_id)
        self.service.add_path('/ProductName', self.product_name)
        self.service.add_path('/Connected', 1)

        # Custom name setting
        def _change_name(p, v):
            # This should fire a change event that will update product_name
            # below.
            settings['name'] = v
            return True

        self.service.add_path('/CustomName', settings['name'], writeable=True,
            onchangecallback=_change_name)

        # We'll count the pulses for all types of services
        self.service.add_path('/Count', value=settings['count'])

    @property
    def product_name(self):
        return self.settings['name'] or self._product_name

    @product_name.setter
    def product_name(self, v):
        # Some pin types don't have an associated service (Disabled pins for
        # example)
        if self.service is not None:
            self.service['/ProductName'] = v or self._product_name

    def deactivate(self):
        self.save_count()
        self.service.__del__()
        del self.service
        self.service = None

    @property
    def level(self):
        return self._level

    @level.setter
    def level(self, l):
        self._level = int(bool(l))

    def toggle(self, level):
        raise NotImplementedError

    def _toggle(self, level, service):
        # Only increment Count on rising edge.
        if level and level != self._level:
            service['/Count'] = (service['/Count']+1) % MAXCOUNT
        self._level = level

    def refresh(self):
        """ Toggle state to last remembered state. This is called if settings
            are changed so the Service can recalculate paths. """
        self.toggle(self._level)

    def save_count(self):
        if self.service is not None:
            self.settings['count'] = self.count

    @property
    def active(self):
        return self.service is not None

    @property
    def count(self):
        return self.service['/Count']

    @count.setter
    def count(self, v):
        self.service['/Count'] = v

    @classmethod
    def createHandler(cls, _type, *args, **kwargs):
        if _type in cls.handlers:
            return cls.handlers[_type](*args, **kwargs)
        return None


class NopPin(object):
    """ Mixin for a pin with empty behaviour. Mix in BEFORE PinHandler so that
        __init__ overrides the base behaviour. """
    def __init__(self, bus, base, path, gpio, settings):
        self.service = None
        self.bus = bus
        self.settings = settings
        self._level = 0 # Remember last state

    def deactivate(self):
        pass

    def toggle(self, level):
        self._level = level

    def save_count(self):
        # Do nothing
        pass

    @property
    def count(self):
        return self.settings['count']

    @count.setter
    def count(self, v):
        pass

    def refresh(self):
        pass


class DisabledPin(NopPin, PinHandler):
    """ Place holder for a disabled pin. """
    _product_name = 'Disabled'
    type_id = 0


class VolumeCounter(PinHandler):
    product_id = 0xA165
    _product_name = "Generic pulse meter"
    dbus_name = "pulsemeter"
    type_id = 1

    def __init__(self, bus, base, path, gpio, settings):
        super(VolumeCounter, self).__init__(bus, base, path, gpio, settings)
        self.service.add_path('/Aggregate', value=self.count*self.rate,
            gettextcallback=lambda p, v: (str(v) + ' cubic meter'))

    @property
    def rate(self):
        return self.settings['rate']

    def toggle(self, level):
        with self.service as s:
            super(VolumeCounter, self)._toggle(level, s)
            s['/Aggregate'] = self.count * self.rate

class TouchEnable(NopPin, PinHandler):
    """ The pin is used to enable/disable the Touch screen when toggled.
        No dbus-service is created. """
    _product_name = 'TouchEnable'
    type_id = 11

    def __init__(self, *args, **kwargs):
        super(TouchEnable, self).__init__(*args, **kwargs)
        self.item = VeDbusItemImport(self.bus,
            "com.victronenergy.settings", "/Settings/Gui/TouchEnabled")

    def toggle(self, level):
        super(TouchEnable, self).toggle(level)

        # Toggle the touch-enable setting on the downward edge.
        # Level is expected to be high with the switch open, and
        # pulled low when pushed.
        if level == 0:
            enabled = bool(self.item.get_value())
            self.item.set_value(int(not enabled))

    def deactivate(self):
        # Always re-enable touch when the pin is deactivated.
        # This adds another layer of protection against accidental
        # lockout.
        self.item.set_value(1)
        del self.item

class PinAlarm(PinHandler):
    product_id = 0xA166
    _product_name = "Generic digital input"
    dbus_name = "digitalinput"
    type_id = 0xFF
    translation = 0 # low, high

    def __init__(self, bus, base, path, gpio, settings):
        super(PinAlarm, self).__init__(bus, base, path, gpio, settings)
        self.service.add_path('/InputState', value=0)
        self.service.add_path('/State', value=self.get_state(0),
            gettextcallback=lambda p, v: TRANSLATIONS[v//2][v%2])
        self.service.add_path('/Alarm', value=self.get_alarm_state(0))

        # Also expose the type
        self.service.add_path('/Type', value=self.type_id,
            gettextcallback=lambda p, v: INPUTTYPES[v])

    def toggle(self, level):
        with self.service as s:
            super(PinAlarm, self)._toggle(level, s)
            s['/InputState'] = bool(level)*1
            s['/State'] = self.get_state(level)
            # Ensure that the alarm flag resets if the /AlarmSetting config option
            # disappears.
            s['/Alarm'] = self.get_alarm_state(level)

    def get_state(self, level):
        state = level ^ self.settings['invert']
        return 2 * self.translation + state

    def get_alarm_state(self, level):
        return 2 * bool(
            (level ^ self.settings['invertalarm']) and self.settings['alarm'])


class Generator(PinAlarm):
    _product_name = "Generator"
    type_id = 9
    translation = 5 # running, stopped

    def __init__(self, *args, **kwargs):
        super(Generator, self).__init__(*args, **kwargs)
        # Periodically rewrite the generator selection. The Multi may reset
        # causing this to be lost, or a race condition on startup may cause
        # it to not be set properly.
        self._timer = GLib.timeout_add(30000,
            lambda: self.select_generator(self.level ^ self.settings['invert'] ^ 1) or True)

#### added for ExtTransferSwitch package
        self.mainVeBusServiceItem = None
#### end added for ExtTransferSwitch package


    def select_generator(self, v):

        # Find all vebus services, and let them know
        try:
            services = [n for n in self.bus.list_names() if n.startswith(
                'com.victronenergy.vebus.')]
            for n in services:
#### added for ExtTransferSwitch package
                # skip this service if it is the main VE.Bus device
                # processing for that is handled in ExtTransferSwitch
                try:
                    if self.mainVeBusServiceItem == None:
                        self.mainVeBusServiceItem = VeDbusItemImport(self.bus,
                            "com.victronenergy.service", "/VebusService")
                    if n == self.mainVeBusService.get_value ():
                        continue
                except:
                    pass
#### end added for ExtTransferSwitch package

                self.bus.call_async(n, '/Ac/Control/RemoteGeneratorSelected', None,
                    'SetValue', 'v', [v], None, None)
        except dbus.exceptions.DBusException:
            print ("DBus exception setting RemoteGeneratorSelected")
            traceback.print_exc()

    def toggle(self, level):
        super(Generator, self).toggle(level)

        # Follow the same inversion sense as for display
        self.select_generator(level ^ self.settings['invert'] ^ 1)

    def deactivate(self):
        super(Generator, self).deactivate()
        # When deactivating, reset the generator selection state
        self.select_generator(0)

        # And kill the periodic job
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

# Various types of things we might want to monitor
class DoorSensor(PinAlarm):
    _product_name = "Door alarm"
    type_id = 2
    translation = 3 # open, closed

class BilgePump(PinAlarm):
    _product_name = "Bilge pump"
    type_id = 3
    translation = 1 # off, on

class BilgeAlarm(PinAlarm):
    _product_name = "Bilge alarm"
    type_id = 4
    translation = 4 # ok, alarm

class BurglarAlarm(PinAlarm):
    _product_name = "Burglar alarm"
    type_id = 5
    translation = 4 # ok, alarm

class SmokeAlarm(PinAlarm):
    _product_name = "Smoke alarm"
    type_id = 6
    translation = 4 # ok, alarm

class FireAlarm(PinAlarm):
    _product_name = "Fire alarm"
    type_id = 7
    translation = 4 # ok, alarm

class CO2Alarm(PinAlarm):
    _product_name = "CO2 alarm"
    type_id = 8
    translation = 4 # ok, alarm

class GenericIO(PinAlarm):
    _product_name = "Generic I/O"
    type_id = 10
    translation = 0 # low, high

#### added for ExtTransferSwitch package
class TransferSwitch(PinAlarm):
    _product_name = "External AC Input transfer switch"
    type_id = 12
    translation = 6 # Grid In / Generator In


def dbusconnection():
    return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()


def main():
    parser = ArgumentParser(description=sys.argv[0])
    parser.add_argument('--servicebase',
        help='Base service name on dbus, default is com.victronenergy',
        default='com.victronenergy')
    parser.add_argument('--poll',
        help='Use a different kind of polling. Options are epoll, dumb and debug',
        default='epoll')
    parser.add_argument('inputs', nargs='+', help='Path to digital input')
    args = parser.parse_args()

    PulseCounter = {
        'debug': DebugPulseCounter,
        'poll': PollingPulseCounter,
    }.get(args.poll, EpollPulseCounter)

    DBusGMainLoop(set_as_default=True)

    # Keep track of enabled services
    services = {}
    inputs = dict(enumerate(args.inputs, 1))
    pulses = PulseCounter() # callable that iterates over pulses

    def register_gpio(path, gpio, bus, settings):
        _type = settings['inputtype']
        print ("Registering GPIO {} for type {}".format(gpio, _type))

        handler = PinHandler.createHandler(_type,
            bus, args.servicebase, path, gpio, settings)
        services[gpio] = handler

        # Only monitor if enabled
        if _type > 0:
            handler.level = pulses.register(path, gpio)
            handler.refresh()

    def unregister_gpio(gpio):
        print ("unRegistering GPIO {}".format(gpio))
        pulses.unregister(gpio)
        services[gpio].deactivate()

    def handle_setting_change(inp, setting, old, new):
        # This handler may also be called if some attribute of a setting
        # is changed, but not the value. Bail if the value is unchanged.
        if old == new:
            return

        if setting == 'inputtype':
            if new:
                # Get current bus and settings objects, to be reused
                service = services[inp]
                bus, settings = service.bus, service.settings

                # Input enabled. If already enabled, unregister the old one first.
                if pulses.registered(inp):
                    unregister_gpio(inp)

                # Before registering the new input, reset its settings to defaults
                settings['count'] = 0
                settings['invert'] = 0
                settings['invertalarm'] = 0
                settings['alarm'] = 0

                # Register it
                register_gpio(inputs[inp], inp, bus, settings)
            elif old:
                # Input disabled
                unregister_gpio(inp)
        elif setting in ('rate', 'invert', 'alarm', 'invertalarm'):
            services[inp].refresh()
        elif setting == 'name':
            services[inp].product_name = new
        elif setting == 'count':
            # Don't want this triggered on a period save, so only execute
            # if it has changed.
            v = int(new)
            s = services[inp]
            if s.count != v:
                s.count = v
                s.refresh()

    for inp, pth in inputs.items():
        supported_settings = {
            'inputtype': ['/Settings/DigitalInput/{}/Type'.format(inp), 0, 0, len(INPUTTYPES)-1],
            'rate': ['/Settings/DigitalInput/{}/Multiplier'.format(inp), 0.001, 0, 1.0],
            'count': ['/Settings/DigitalInput/{}/Count'.format(inp), 0, 0, MAXCOUNT, 1],
            'invert': ['/Settings/DigitalInput/{}/InvertTranslation'.format(inp), 0, 0, 1],
            'invertalarm': ['/Settings/DigitalInput/{}/InvertAlarm'.format(inp), 0, 0, 1],
            'alarm': ['/Settings/DigitalInput/{}/AlarmSetting'.format(inp), 0, 0, 1],
            'name': ['/Settings/DigitalInput/{}/CustomName'.format(inp), '', '', ''],
        }
        bus = dbusconnection()
        sd = SettingsDevice(bus, supported_settings, partial(handle_setting_change, inp), timeout=10)
        register_gpio(pth, inp, bus, sd)

    def poll(mainloop):
        from time import time
        idx = 0

        try:
            for inp, level in pulses():
                # epoll object only resyncs once a second. We may receive
                # a pulse for something that's been deregistered.
                try:
                    services[inp].toggle(level)
                except KeyError:
                    continue
        except:
            traceback.print_exc()
            mainloop.quit()

    # Need to run the gpio polling in separate thread. Pass in the mainloop so
    # the thread can kill us if there is an exception.
    mainloop = GLib.MainLoop()

    poller = Thread(target=lambda: poll(mainloop))
    poller.daemon = True
    poller.start()

    # Periodically save the counter
    def save_counters():
        for inp in inputs:
            services[inp].save_count()
        return True
    GLib.timeout_add(SAVEINTERVAL, save_counters)

    # Save counter on shutdown
    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))

    try:
        mainloop.run()
    except KeyboardInterrupt:
        pass
    finally:
        save_counters()

if __name__ == "__main__":
    main()
