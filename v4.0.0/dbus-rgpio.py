#!/usr/bin/env python3

# #############################################################################
#
#   dbus-rgpio.py
#
#   A Victron Venus OS driver to integrate multiple generic RGPIO (MQTT-based)
#   I/O devices, supporting both Digital Inputs and Relays (Switches).
#
#   - Manages a kernel module for virtual GPIOs (Inputs)
#   - Creates D-Bus services for relays (com.victronenergy.switch)
#   - Uses a persistent mapping file for stable GPIO assignments
#   - Dynamically reconfigures on changes to config.ini
#
# #############################################################################

import configparser
import paho.mqtt.client as mqtt
import os
import sys
import logging
import time
import subprocess
import re
import shutil
import platform
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop

# Make sure the path includes Victron libraries
sys.path.insert(1, '/opt/victronenergy/dbus-digitalinputs/ext/velib_python')
from vedbus import VeDbusService
from settingsdevice import SettingsDevice

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RgpioDriver")

# --- CONSTANTS ---
CONFIG_FILE = '/data/RemoteGPIO/conf/config.ini'
MAPPING_FILE = '/data/RemoteGPIO/conf/rgpio_mapping.ini'
MODULE_NAME = 'rgpio_module'
MODULE_PATH = f'/data/RemoteGPIO/{MODULE_NAME}.ko'
MODULE_CAPACITY = 64
CONFIG_CHECK_INTERVAL = 10 # Seconds
DBUS_SERVICE_PATH = '/service/dbus-digitalinputs'

# =================================================================
# KERNEL MODULE & SYSFS MANAGEMENT (for Digital Inputs)
# =================================================================

def get_device_configs(config_path):
    """Reads config and returns a dictionary of device configurations."""
    devices = {}
    try:
        config = configparser.ConfigParser()
        config.read(config_path)
        for section in config.sections():
            if section.startswith('device_'):
                if 'serial' in config[section]:
                    devices[section] = dict(config[section])
    except Exception as e:
        logger.error(f"Error reading device configs: {e}")
    return devices

def manage_kernel_module(module_path, capacity):
    """
    Ensures the kernel module is loaded with a fixed capacity. Does not unload.
    Returns a tuple (base_gpio, trigger_path, capacity) on success, otherwise (None, None, 0).
    """
    # Check if module is already loaded
    lsmod_result = subprocess.run(["lsmod"], capture_output=True, text=True)
    if MODULE_NAME in lsmod_result.stdout:
        logger.info(f"Module '{MODULE_NAME}' is already loaded. Using existing instance.")
        try:
            dmesg_output = subprocess.run(["dmesg"], capture_output=True, text=True).stdout
            match = None
            for line in reversed(dmesg_output.strip().split('\n')):
                m = re.search(r"rgpio_module:.*base (\d+)", line)
                if m:
                    match = m
                    break
            base_gpio = int(match.group(1))
            ngpio_path = f"/sys/class/gpio/gpiochip{base_gpio}/ngpio"
            with open(ngpio_path, 'r') as f:
                current_capacity = int(f.read().strip())
            
            trigger_path_base = f"/sys/devices/platform/{MODULE_NAME}"
            if not os.path.exists(os.path.join(trigger_path_base, "trigger_irq")):
                 trigger_path_base = f"/sys/devices/platform/{MODULE_NAME}.0" # Fallback
            trigger_path = os.path.join(trigger_path_base, "trigger_irq")
            
            logger.info(f"Detected module capacity: {current_capacity}, Base: {base_gpio}")
            return base_gpio, trigger_path, current_capacity
        except Exception as e:
            logger.critical(f"Could not verify existing module, a reboot may be required. Error: {e}")
            return None, None, 0
    
    # Module not loaded, proceed with a clean load
    logger.info(f"Module not loaded. Attempting to load with capacity={capacity}...")
    try:
        cmd = ["insmod", module_path, f"num_gpios={capacity}"]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("Kernel module loaded successfully.")
        time.sleep(0.5)
        
        return manage_kernel_module(module_path, capacity) # Re-call to get info

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to load kernel module: {e.stderr.strip()}")
        return None, None, 0

def manage_exported_gpios(gpio_base, offsets_to_export, offsets_to_unexport):
    """Exports or unexports specific GPIOs based on their offsets."""
    changed = False
    if offsets_to_export:
        logger.info(f"Exporting new GPIOs at offsets: {offsets_to_export}")
        changed = True
        for offset in offsets_to_export:
            gpio_num = gpio_base + offset
            try:
                if not os.path.exists(f"/sys/class/gpio/gpio{gpio_num}"):
                    with open("/sys/class/gpio/export", 'w') as f: f.write(str(gpio_num))
                    time.sleep(0.05)
            except Exception as e:
                logger.warning(f"Could not export GPIO {gpio_num}: {e}")
    
    if offsets_to_unexport:
        logger.info(f"Unexporting obsolete GPIOs at offsets: {offsets_to_unexport}")
        changed = True
        for offset in offsets_to_unexport:
            gpio_num = gpio_base + offset
            try:
                if os.path.exists(f"/sys/class/gpio/gpio{gpio_num}"):
                    with open("/sys/class/gpio/unexport", 'w') as f: f.write(str(gpio_num))
            except Exception as e:
                logger.warning(f"Could not unexport GPIO {gpio_num}: {e}")
    return changed

# NEW: Re-introduced create_io_ext_files
def create_io_ext_files(config_path, persistent_map, gpio_base):
    """Creates the /run/io-ext structure based on the persistent mapping."""
    logger.info("Rebuilding io-ext configuration files and symlinks...")
    io_ext_dir = "/run/io-ext"
    os.makedirs(io_ext_dir, exist_ok=True)
    
    config = configparser.ConfigParser()
    config.read(config_path)
    
    current_safe_serials = set()

    for section in config.sections():
        if section.startswith('device_'):
            serial_raw = config[section]['serial']
            serial_safe = serial_raw.replace('-', '_')
            current_safe_serials.add(serial_safe)

            num_inputs = int(config[section].get('num_inputs', 0))
            num_relays = int(config[section].get('num_relays', 0))
            
            device_dir = f"{io_ext_dir}/{serial_safe}"
            os.makedirs(device_dir, exist_ok=True)
            
            pins_content = [f"tag\t{serial_safe}"]
            for i in range(1, num_inputs + 1):
                pins_content.append(f"input\t{device_dir}/input_{i} {i}")
                unique_id = f"{serial_raw}_input_{i}"
                if unique_id in persistent_map:
                    offset = persistent_map[unique_id]
                    gpio_num = gpio_base + offset
                    link_target = f"/sys/class/gpio/gpio{gpio_num}"
                    link_path = os.path.join(device_dir, f"input_{i}")
                    if os.path.lexists(link_path): os.remove(link_path)
                    os.symlink(link_target, link_path)
            
            for i in range(1, num_relays + 1):
                pins_content.append(f"relay\t{device_dir}/relay_{i} {i}")
            
            with open(os.path.join(device_dir, "pins.conf"), 'w') as f:
                f.write("\n".join(pins_content) + "\n")
    logger.info("io-ext rebuild complete.")


def cleanup_on_exit(driver_instance):
    """Unexports all used GPIOs and cleans up our io-ext files on exit."""
    logger.info("Performing cleanup on exit...")
    
    if driver_instance.persistent_map and driver_instance.gpio_base is not None:
        offsets_to_unexport = list(driver_instance.persistent_map.values())
        manage_exported_gpios(driver_instance.gpio_base, [], offsets_to_unexport)
    
    io_ext_dir = "/run/io-ext"
    try:
        for serial_safe in driver_instance.active_safe_serials:
            device_dir = os.path.join(io_ext_dir, serial_safe)
            if os.path.exists(device_dir):
                logger.info(f"  - Removing {device_dir}")
                shutil.rmtree(device_dir)
        
        if os.path.exists(io_ext_dir) and not os.listdir(io_ext_dir):
            logger.info(f"  - Removing empty parent directory {io_ext_dir}")
            os.rmdir(io_ext_dir)
    except Exception as e:
        logger.error(f"Error during io-ext cleanup: {e}")

# =================================================================
# MAIN DRIVER CLASS
# =================================================================

class RgpioDriver:
    def __init__(self, gpio_base, trigger_path, config_path, mapping_path, module_capacity):
        self.gpio_base = gpio_base
        self.trigger_file = trigger_path
        self.config_path = config_path
        self.mapping_path = mapping_path
        self.module_capacity = module_capacity
        
        self.client = None
        self.input_mqtt_map = {}
        self.relay_mqtt_map = {}
        self.persistent_map = self._load_persistent_map()
        self.active_safe_serials = set()
        
        self.relay_services = {}
        
        self.reconfigure() # Initial configuration

    def _load_persistent_map(self):
        logger.info(f"Loading persistent GPIO map from {self.mapping_path}")
        mapping = {}
        try:
            parser = configparser.ConfigParser()
            parser.read(self.mapping_path)
            if 'mapping' in parser:
                for key, value in parser['mapping'].items():
                    mapping[key] = int(value)
        except Exception:
            logger.warning(f"Could not load mapping file, will create a new one.")
        return mapping

    def _save_persistent_map(self):
        logger.info(f"Saving persistent GPIO map to {self.mapping_path}")
        parser = configparser.ConfigParser()
        parser['mapping'] = {key: str(value) for key, value in self.persistent_map.items()}
        try:
            with open(self.mapping_path, 'w') as f:
                parser.write(f)
        except Exception as e:
            logger.error(f"Could not save mapping file: {e}")

    def reconfigure(self):
        logger.info("Reconfiguring driver...")
        
        device_configs = get_device_configs(self.config_path)
        required_inputs_count = sum(int(d.get('num_inputs', 0)) for d in device_configs.values())
        
        if required_inputs_count > self.module_capacity:
            logger.error(f"Configuration requires {required_inputs_count} GPIOs, but module only provides {self.module_capacity}.")
            return

        # --- Update Persistent Mapping for Inputs ---
        old_offsets = set(self.persistent_map.values())
        new_persistent_map = {}
        new_input_mqtt_map = {}
        used_offsets = set(self.persistent_map.values())

        for cfg in device_configs.values():
            serial_raw = cfg['serial']
            num_inputs = int(cfg.get('num_inputs', 0))
            topic_base = cfg['topic_base']
            for i in range(1, num_inputs + 1):
                unique_id = f"{serial_raw}_input_{i}"
                if unique_id in self.persistent_map:
                    offset = self.persistent_map[unique_id]
                else:
                    offset = 0
                    while offset in used_offsets: offset += 1
                    logger.info(f"Assigning new offset {offset} to {unique_id}")
                    used_offsets.add(offset)
                new_persistent_map[unique_id] = offset
                new_input_mqtt_map[f"{topic_base}/input/{i}"] = offset
        
        new_offsets = set(new_persistent_map.values())
        offsets_to_export = new_offsets - old_offsets
        offsets_to_unexport = old_offsets - new_offsets
        
        gpio_state_changed = manage_exported_gpios(self.gpio_base, offsets_to_export, offsets_to_unexport)

        # --- Update Relay Services and Mappings ---
        self.relay_mqtt_map.clear()
        new_safe_serials = set()
        for cfg in device_configs.values():
            serial_raw = cfg['serial']
            serial_safe = serial_raw.replace('-', '_')
            new_safe_serials.add(serial_safe)

            if serial_safe not in self.relay_services:
                logger.info(f"Creating new D-Bus Switch service for {serial_raw}")
                bus = dbus.SystemBus(private=True) if (platform.machine() == 'armv7l') else dbus.SessionBus(private=True)
                self.relay_services[serial_safe] = DbusRgpioSwitchService(cfg, self, bus)
            
            topic_base = cfg['topic_base']
            num_relays = int(cfg.get('num_relays', 0))
            for i in range(num_relays):
                state_topic = f"{topic_base}/relay/{i+1}/state"
                self.relay_mqtt_map[state_topic] = {'serial_safe': serial_safe, 'index': i}

        serials_to_remove = self.active_safe_serials - new_safe_serials
        for serial in serials_to_remove:
            logger.info(f"Removing obsolete D-Bus Switch service for {serial}")
            if serial in self.relay_services:
                del self.relay_services[serial]
        
        self.persistent_map = new_persistent_map
        old_topics = set(self.input_mqtt_map.keys())
        self.input_mqtt_map = new_input_mqtt_map
        new_topics = set(self.input_mqtt_map.keys())
        self.active_safe_serials = new_safe_serials

        all_new_topics = new_topics.union(set(self.relay_mqtt_map.keys()))
        all_old_topics = old_topics.union(set(self.relay_mqtt_map.keys()))
        if self.client and self.client.is_connected():
            if all_old_topics - all_new_topics: self.client.unsubscribe(list(all_old_topics - all_new_topics))
            if all_new_topics - all_old_topics: self.client.subscribe([(t, 0) for t in all_new_topics - all_old_topics])
        
        # RESTORED: Call to create io-ext files
        create_io_ext_files(self.config_path, self.persistent_map, self.gpio_base)
        self._save_persistent_map()
        
        if gpio_state_changed:
            logger.info(f"GPIO state changed, restarting '{DBUS_SERVICE_PATH}'...")
            subprocess.run(["svc", "-t", DBUS_SERVICE_PATH])

        logger.info(f"Reconfiguration complete. Monitoring {len(self.input_mqtt_map)} inputs and {len(self.relay_services)} relay devices.")

    def on_mqtt_message(self, client, userdata, msg):
        if msg.topic in self.input_mqtt_map:
            self._handle_input_message(msg.topic, msg.payload)
        elif msg.topic in self.relay_mqtt_map:
            self._handle_relay_message(msg.topic, msg.payload)

    def _handle_input_message(self, topic, payload):
        virtual_line = self.input_mqtt_map.get(topic)
        if virtual_line is None: return
        try:
            gpio_num = self.gpio_base + virtual_line
            with open(f"/sys/class/gpio/gpio{gpio_num}/direction", 'w') as f: f.write('out')
            with open(f"/sys/class/gpio/gpio{gpio_num}/value", 'w') as f: f.write(payload.decode())
            with open(f"/sys/class/gpio/gpio{gpio_num}/direction", 'w') as f: f.write('in')
            with open(self.trigger_file, "w") as f: f.write(str(virtual_line))
        except Exception as e:
            logger.error(f"Error processing input message for {topic}: {e}")

    def _handle_relay_message(self, topic, payload):
        mapping = self.relay_mqtt_map.get(topic)
        if mapping:
            serial_safe = mapping['serial_safe']
            index = mapping['index']
            if serial_safe in self.relay_services:
                self.relay_services[serial_safe].update_state_from_mqtt(index, payload.decode())

    def publish_relay_state(self, topic_base, index, state):
        if self.client and self.client.is_connected():
            payload = "ON" if state == 1 else "OFF"
            command_topic = f"{topic_base}/relay/{index}/set"
            self.client.publish(command_topic, payload)
            logger.info(f"Published MQTT message: Topic={command_topic}, Payload={payload}")

    def start(self):
        config = configparser.ConfigParser()
        config.read(self.config_path)
        broker_config = config['mqtt_broker']
        
        self.client = mqtt.Client(1)
        self.client.on_message = self.on_mqtt_message
        
        if broker_config.get('username'):
            self.client.username_pw_set(broker_config.get('username'), broker_config.get('password'))
        
        self.client.connect(broker_config['address'], int(broker_config['port']), 60)
        
        all_topics = set(self.input_mqtt_map.keys()).union(set(self.relay_mqtt_map.keys()))
        if all_topics:
            self.client.subscribe([(t, 0) for t in all_topics])
        
        self.client.loop_start()
        logger.info("MQTT bridge started in background.")

    def stop(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT bridge stopped.")

# =================================================================
# D-BUS SERVICE CLASS for a SINGLE RELAY DEVICE
# =================================================================

class DbusRgpioSwitchService:
    def __init__(self, device_config, parent_driver, bus):
        self.config = device_config
        self.parent_driver = parent_driver
        
        self.serial = self.config.get('serial', 'RGPIO-IO-???')
        self.num_relays = int(self.config.get('num_relays', 8))
        self.topic_base = self.config.get('topic_base', f'rgpio/{self.serial}')
        
        serial_safe = self.serial.replace('-', '_')
        self.servicename = f'com.victronenergy.switch.{serial_safe}'
        
        self._dbusservice = VeDbusService(self.servicename, bus=bus, register=False)
        
        # --- Create Settings ---
        self._settings = self._setup_settings()

        # --- Create D-Bus paths ---
        self._dbusservice.add_path('/Management/ProcessName', __file__)
        self._dbusservice.add_path('/Management/ProcessVersion', '1.0 (dbus-rgpio)')
        self._dbusservice.add_path('/Management/Connection', 'RGPIO MQTT Bridge')

        self._dbusservice.add_path('/DeviceInstance', int(self.config.get('device_instance', 50)))
        self._dbusservice.add_path('/ProductId', 19191)
        self._dbusservice.add_path('/ProductName', 'RGPIO IO Extender')
        self._dbusservice.add_path('/FirmwareVersion', '1.0')
        self._dbusservice.add_path('/HardwareVersion', 'N/A')
        self._dbusservice.add_path('/Connected', 1)
        self._dbusservice.add_path('/Serial', self.serial)
        self._dbusservice.add_path('/State', 256) # 256=Connected

        self._dbusservice.add_path(
            path='/CustomName',
            value=self._settings['CustomName'],
            writeable=True,
            onchangecallback=lambda p, v: self._handle_writable_setting_change('CustomName', p, v)
        )
        
        for i in range(self.num_relays):
            self._create_relay_paths(i)
            
        self._dbusservice.register()

    def _setup_settings(self):
        """Creates the SettingsDevice object and defines supported settings."""
        settings_id = self.servicename.replace('.', '_')
        settings_path_prefix = f'/Settings/Devices/{settings_id}'
        
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
        
        return SettingsDevice(self._dbusservice._dbusconn, supported_settings, None)

    def _create_relay_paths(self, relay_index):
        """Creates all D-Bus paths for a single relay, loading values from settings."""
        relay_id = relay_index + 1
        dbus_base_path = f'/SwitchableOutput/relay_{relay_id}'
        
        self._dbusservice.add_path(
            path=f'{dbus_base_path}/State',
            value=self._settings[f'Relay{relay_id}State'],
            writeable=True,
            onchangecallback=lambda path, value, index=relay_index: self._handle_relay_state_change(index, path, value)
        )
        
        self._dbusservice.add_path(f'{dbus_base_path}/Name', f'Relay {relay_id}')
        self._dbusservice.add_path(f'{dbus_base_path}/Status', 0)
        self._dbusservice.add_path(f'{dbus_base_path}/Settings/ValidFunctions', 4)
        self._dbusservice.add_path(f'{dbus_base_path}/Settings/ValidTypes', 3)

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
        """Callback for when a writable setting is changed from D-Bus."""
        self._settings[settings_dict_key] = value
        return True

    def _handle_relay_state_change(self, index, path, value):
        logger.info(f"Device {self.serial}: Relay {index+1} state change requested via D-Bus to {value}")
        self._settings[f'Relay{index+1}State'] = value
        self.parent_driver.publish_relay_state(self.topic_base, index, value)
        return True

    def update_state_from_mqtt(self, index, payload):
        new_state = 1 if payload == "ON" else 0
        relay_id = index + 1
        dbus_path = f'/SwitchableOutput/relay_{relay_id}/State'
        
        if self._dbusservice[dbus_path] != new_state:
            logger.info(f"Device {self.serial}: Relay {relay_id} state updated to {new_state} from MQTT.")
            self._dbusservice[dbus_path] = new_state
            self._settings[f'Relay{relay_id}State'] = new_state

# =================================================================
# MAIN EXECUTION
# =================================================================

if __name__ == "__main__":
    DBusGMainLoop(set_as_default=True)
    
    logger.info("--- Starting RGPIO Unified Driver ---")
    
    gpio_base_num, trigger_path, module_capacity = manage_kernel_module(
        module_path=MODULE_PATH, capacity=MODULE_CAPACITY)
    
    if gpio_base_num is None:
        logger.critical("Could not configure kernel module. The script will exit.")
        sys.exit(1)
    
    driver = RgpioDriver(
        gpio_base=gpio_base_num, 
        trigger_path=trigger_path, 
        config_path=CONFIG_FILE,
        mapping_path=MAPPING_FILE,
        module_capacity=module_capacity
    )
    driver.start()

    from gi.repository import GLib
    mainloop = GLib.MainLoop()
    
    def check_config_callback():
        try:
            current_mtime = os.path.getmtime(CONFIG_FILE)
            global last_config_mtime
            if current_mtime != last_config_mtime:
                logger.info("Configuration file change detected.")
                last_config_mtime = current_mtime
                driver.reconfigure()
        except FileNotFoundError:
            logger.warning(f"Configuration file '{CONFIG_FILE}' not found. Skipping check.")
        return True

    last_config_mtime = os.path.getmtime(CONFIG_FILE)
    GLib.timeout_add_seconds(CONFIG_CHECK_INTERVAL, check_config_callback)
    
    try:
        mainloop.run()
    except KeyboardInterrupt:
        logger.info("Script shutdown requested by user.")
    finally:
        driver.stop()
        cleanup_on_exit(driver)
        logger.info("--- RGPIO Unified Driver stopped ---")

