#!/usr/bin/env python

# #############################################################################
#
#   dbus-rgpio-switch.py
#
#   A Victron Venus OS driver to integrate multiple generic RGPIO (MQTT-based)
#   I/O devices, with persistent settings and external configuration.
#
#   This script acts as a launcher, forking a separate process for each
#   device defined in the configuration file.
#
#   Reads configuration from /data/RemoteGPIO/conf/config.ini
#
# #############################################################################

from gi.repository import GLib
import logging
import sys
import os
import subprocess
import threading
import platform
import dbus
import configparser

# Make sure the path includes Victron libraries
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from vedbus import VeDbusService
from settingsdevice import SettingsDevice

# Configuration file path
CONFIG_FILE_PATH = '/data/RemoteGPIO/conf/config.ini'

class DbusRgpioIoService:
    def __init__(self, device_config, broker_config):
        self.config = device_config
        self.broker_config = broker_config
        
        # Extract config values with defaults
        self.serial = self.config.get('serial', 'RGPIO-IO-???')
        self.num_relays = self.config.getint('num_relays', 8)
        self.topic_base = self.config.get('topic_base', f'rgpio/{self.serial}')
        self.device_instance = self.config.getint('device_instance', 50)
        self.servicename = f'com.victronenergy.switch.rgpio_io_{self.device_instance}'

        # Use the modern registration method
        self._dbusservice = VeDbusService(self.servicename, register=False)
        self._is_connected = False
        self._listener_thread = None
        self._dbus_path_map = {}

        logging.info(f"Starting RGPIO Driver for device {self.serial} (Instance: {self.device_instance})")

        # Create the management D-Bus entries
        self._dbusservice.add_path('/Management/ProcessName', __file__)
        self._dbusservice.add_path('/Management/ProcessVersion', '3.6')
        self._dbusservice.add_path('/Management/Connection', f'RGPIO (MQTT): {self.broker_config.get("address", "N/A")}')

        # Create device-level D-Bus entries
        self._dbusservice.add_path('/DeviceInstance', self.device_instance)
        self._dbusservice.add_path('/ProductId', 19191)
        self._dbusservice.add_path('/ProductName', 'RGPIO IO extender')
        self._dbusservice.add_path('/FirmwareVersion', '3.6 (dbus-rgpio-switch)')
        self._dbusservice.add_path('/HardwareVersion', 'N/A')
        self._dbusservice.add_path('/Connected', 0) # Start as disconnected
        self._dbusservice.add_path('/Serial', self.serial)
        self._dbusservice.add_path('/State', 0) # Start as disconnected (0=Disconnected, 256=Connected)

        # ---- Persistent Settings ----
        self._settings = self._setup_settings()
        
        # Add persistent CustomName path for the device
        custom_name_key = 'CustomName'
        self._dbusservice.add_path(
            path='/CustomName',
            value=self._settings[custom_name_key],
            writeable=True,
            onchangecallback=lambda p, v, key=custom_name_key: self._handle_writable_setting_change(key, p, v)
        )

        # ---- Create Relay Paths ----
        logging.info(f"Creating {self.num_relays} relays for {self.serial}...")
        for i in range(self.num_relays):
            self._create_relay_paths(i)

        # Now that all paths are added, register the service
        self._dbusservice.register()

        # Start listening for MQTT messages
        self.start_mqtt_listener()

    def _setup_settings(self):
        """ Crée l'objet SettingsDevice et définit les paramètres supportés. """
        settings_path_prefix = f'/Settings/Devices/rgpio_io_{self.device_instance}'
        
        supported_settings = {
            'CustomName': [f'{settings_path_prefix}/CustomName', f'RGPIO Module ({self.serial})', 0, 0]
        }
        for i in range(self.num_relays):
            relay_id = i + 1
            supported_settings[f'Relay{relay_id}State'] = [f'{settings_path_prefix}/Relay/{relay_id}/State', 0, 0, 1]
            supported_settings[f'Relay{relay_id}CustomName'] = [f'{settings_path_prefix}/Relay/{relay_id}/CustomName', '', 0, 0]
            supported_settings[f'Relay{relay_id}Function'] = [f'{settings_path_prefix}/Relay/{relay_id}/Function', 2, 0, 0]
            supported_settings[f'Relay{relay_id}Group'] = [f'{settings_path_prefix}/Relay/{relay_id}/Group', '', 0, 0]
            supported_settings[f'Relay{relay_id}ShowUIControl'] = [f'{settings_path_prefix}/Relay/{relay_id}/ShowUIControl', 1, 0, 1]
            supported_settings[f'Relay{relay_id}Type'] = [f'{settings_path_prefix}/Relay/{relay_id}/Type', 1, 0, 0]
        
        bus = dbus.SystemBus() if (platform.machine() == 'armv7l') else dbus.SessionBus()
        # Pass None as the callback to disable live updates from the settings service
        return SettingsDevice(bus, supported_settings, None)

    def _create_relay_paths(self, relay_index):
        """ Crée tous les chemins D-Bus pour un seul relais, en chargeant les valeurs depuis les paramètres. """
        relay_id = relay_index + 1
        dbus_base_path = f'/SwitchableOutput/relay_{relay_id}'
        state_settings_key = f'Relay{relay_id}State'
        
        # Controllable and persistent state
        self._dbusservice.add_path(
            path=f'{dbus_base_path}/State',
            value=self._settings[state_settings_key],
            writeable=True,
            onchangecallback=lambda path, value, index=relay_index: self._handle_relay_state_change(index, path, value)
        )
        
        # Static info
        self._dbusservice.add_path(f'{dbus_base_path}/Name', f'RGPIO Relay {relay_id}')
        self._dbusservice.add_path(f'{dbus_base_path}/Status', 0)
        self._dbusservice.add_path(f'{dbus_base_path}/Settings/ValidFunctions', 4)
        self._dbusservice.add_path(f'{dbus_base_path}/Settings/ValidTypes', 3)

        # Writable settings paths that are persistent
        settings_to_create = {
            'CustomName': f'Relay{relay_id}CustomName',
            'Function': f'Relay{relay_id}Function',
            'Group': f'Relay{relay_id}Group',
            'ShowUIControl': f'Relay{relay_id}ShowUIControl',
            'Type': f'Relay{relay_id}Type'
        }

        for setting_key, settings_dict_key in settings_to_create.items():
            dbus_path = f'{dbus_base_path}/Settings/{setting_key}'
            self._dbusservice.add_path(
                path=dbus_path,
                value=self._settings[settings_dict_key],
                writeable=True,
                onchangecallback=lambda p, v, key=settings_dict_key: self._handle_writable_setting_change(key, p, v)
            )

    def _handle_writable_setting_change(self, settings_dict_key, dbus_path, value):
        self._settings[settings_dict_key] = value
        return True

    def _set_connection_state(self, connected):
        if connected == self._is_connected:
            return False
        
        if connected:
            logging.info(f"Device {self.serial}: Connection established.")
            self._dbusservice['/State'] = 256
            self._dbusservice['/Connected'] = 1
        else:
            logging.warning(f"Device {self.serial}: Connection lost.")
            self._dbusservice['/State'] = 0
            self._dbusservice['/Connected'] = 0
            logging.info(f"Device {self.serial}: Attempting to restart listener in 10 seconds...")
            GLib.timeout_add_seconds(10, self._restart_listener)
        
        self._is_connected = connected
        return False

    def _restart_listener(self):
        if not self._is_connected:
            self.start_mqtt_listener()
        return False

    def start_mqtt_listener(self):
        if self._listener_thread and self._listener_thread.is_alive():
            return

        logging.info(f"Device {self.serial}: Starting Mosquitto listener...")
        topic_to_subscribe = f"{self.topic_base}/relay/+/state"
        cmd = [
            'mosquitto_sub', '-h', self.broker_config.get('address'), '-p', self.broker_config.get('port'),
            '-t', topic_to_subscribe, '-F', '%t %p',
            '-i', f'dbus-rgpio-{self.serial}-sub',
        ]
        if self.broker_config.get('username'):
            cmd.extend(['-u', self.broker_config.get('username')])
        if self.broker_config.get('password'):
            cmd.extend(['-P', self.broker_config.get('password')])

        self._listener_thread = threading.Thread(target=self._run_listener, args=(cmd,), daemon=True)
        self._listener_thread.start()

    def _run_listener(self, cmd):
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for line in iter(process.stdout.readline, ''):
                if not self._is_connected:
                    GLib.idle_add(self._set_connection_state, True)
                try:
                    topic, payload = line.strip().split(' ', 1)
                    parts = topic.split('/')
                    if len(parts) == 4 and parts[1] == 'relay':
                        index = int(parts[2])
                        GLib.idle_add(self._update_state_from_mqtt, index, payload)
                except (ValueError, IndexError):
                    pass
        except Exception as e:
            logging.error(f"Device {self.serial}: Error in Mosquitto listener thread: {e}")
        finally:
            if self._is_connected:
                GLib.idle_add(self._set_connection_state, False)

    def _update_state_from_mqtt(self, index, payload):
        if 0 <= index < self.num_relays:
            new_state = 1 if payload == "ON" else 0
            relay_id = index + 1
            state_settings_key = f'Relay{relay_id}State'
            dbus_path = f'/SwitchableOutput/relay_{relay_id}/State'
            
            if self._dbusservice.get_value(dbus_path) != new_state:
                logging.info(f"Device {self.serial}: Relay {relay_id} state updated to {new_state} from MQTT.")
                self._dbusservice.set_value(dbus_path, new_state)
                self._settings[state_settings_key] = new_state
        return False

    def _handle_relay_state_change(self, index, path, value):
        relay_id = index + 1
        if not self._is_connected:
            logging.warning(f"Device {self.serial}: Cannot change relay {relay_id}: RGPIO device is disconnected.")
            return False

        logging.info(f"Device {self.serial}: Relay {relay_id} state change requested via D-Bus to {value}")
        
        state_settings_key = f'Relay{relay_id}State'
        self._settings[state_settings_key] = value
        
        payload_to_send = "ON" if value == 1 else "OFF"
        command_topic = f"{self.topic_base}/relay/{index}/set"
        cmd = [
            'mosquitto_pub', '-h', self.broker_config.get('address'), '-p', self.broker_config.get('port'),
            '-t', command_topic, '-m', payload_to_send,
            '-i', f'dbus-rgpio-{self.serial}-pub'
        ]
        if self.broker_config.get('username'):
            cmd.extend(['-u', self.broker_config.get('username')])
        if self.broker_config.get('password'):
            cmd.extend(['-P', self.broker_config.get('password')])

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except Exception as e:
            logging.error(f"Device {self.serial}: Error sending Mosquitto command for relay {relay_id}: {e}")
            return False
        return True

def create_default_config(path):
    """ Crée un fichier de configuration par défaut s'il n'existe pas. """
    config_dir = os.path.dirname(path)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    
    config = configparser.ConfigParser()
    config['mqtt_broker'] = {
        'address': 'localhost',
        'port': '1883',
        'username': '',
        'password': ''
    }
    config['device_1'] = {
        'serial': 'RGPIO-IO-001',
        'topic_base': 'dingtian/1',
        'num_relays': '8',
        'device_instance': '50'
    }
    config['device_2'] = {
        'serial': 'RGPIO-IO-002',
        'topic_base': 'dingtian/2',
        'num_relays': '4',
        'device_instance': '51'
    }
    with open(path, 'w') as configfile:
        config.write(configfile)
    logging.info(f"Created default configuration file at {path}")

def run_device_service(device_config, broker_config):
    """
    This function is executed in a child process.
    It sets up the D-Bus main loop and runs the service for a single device.
    """
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    
    DbusRgpioIoService(device_config, broker_config)
    
    logging.info(f"D-Bus service for device {device_config.get('serial')} started. Entering main loop.")
    mainloop = GLib.MainLoop()
    mainloop.run()

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)

    if not os.path.exists(CONFIG_FILE_PATH):
        create_default_config(CONFIG_FILE_PATH)

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE_PATH)

    try:
        broker_config = config['mqtt_broker']
    except KeyError:
        logging.error(f"Configuration error: [mqtt_broker] section not found in {CONFIG_FILE_PATH}. Exiting.")
        sys.exit(1)
    
    # Fork a child process for each [device_X] section
    child_pids = []
    for section in config.sections():
        if section.startswith('device_'):
            pid = os.fork()
            
            if pid > 0:
                # Parent process
                child_pids.append(pid)
                logging.info(f"Launched process {pid} for device configuration '{section}'.")
            else:
                # Child process
                device_config = config[section]
                try:
                    # The child process starts its own main loop and never returns from this call.
                    run_device_service(device_config, broker_config)
                except Exception as e:
                    logging.error(f"Error in child process for device '{section}': {e}")
                finally:
                    # Ensure child process exits cleanly if run_device_service ever returns.
                    sys.exit(0)

    # Parent process can now exit. The child processes will continue to run as daemons.
    logging.info(f"Parent process has launched all device handlers: {child_pids}. Exiting.")
    sys.exit(0)


if __name__ == "__main__":
    main()
