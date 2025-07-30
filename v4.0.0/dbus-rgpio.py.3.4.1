#!/usr/bin/env python3

# #############################################################################
#
#   dbus-rgpio.py (Core Engine)
#
#   Version: 3.4.1
#
#   Manages virtual GPIOs and D-Bus services, exposing an internal API
#   for external communication modules to register devices.
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
import json
import signal
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

# Make sure the path includes Victron libraries
sys.path.insert(1, '/opt/victronenergy/dbus-digitalinputs/ext/velib_python')
from vedbus import VeDbusService
from settingsdevice import SettingsDevice

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RgpioEngine")

# --- CONSTANTS ---
MAPPING_FILE = '/data/RemoteGPIO/conf/rgpio_mapping.ini'
MODULE_NAME = 'rgpio_module'
MODULE_PATH = f'/data/RemoteGPIO/{MODULE_NAME}.ko'
MODULE_CAPACITY = 64
DBUS_SERVICE_PATH = '/service/dbus-digitalinputs'
# Internal API MQTT Topics
API_TOPIC_BASE = "rgpio/api"
API_INPUT_STATE_TOPIC = f"{API_TOPIC_BASE}/input/state"
API_RELAY_SET_TOPIC = f"{API_TOPIC_BASE}/relay/set"
API_HEARTBEAT_TOPIC = f"{API_TOPIC_BASE}/heartbeat"
API_DEVICE_REGISTER_TOPIC = f"{API_TOPIC_BASE}/device/register"
API_DEVICE_STATUS_TOPIC = f"{API_TOPIC_BASE}/device/status"
API_DEVICE_RELAY_NAME_TOPIC = f"{API_TOPIC_BASE}/device"


# --- MQTT Client Compatibility ---
try:
    from paho.mqtt.enums import CallbackAPIVersion
    MQTT_CLIENT_ARGS = {'callback_api_version': CallbackAPIVersion.VERSION1}
    logger.info("Configured for paho-mqtt v2.x")
except ImportError:
    MQTT_CLIENT_ARGS = {}
    logger.info("Configured for paho-mqtt v1.x")

# =================================================================
# KERNEL MODULE & SYSFS MANAGEMENT
# =================================================================

def manage_kernel_module(module_path, capacity):
    # Ensures the kernel module is loaded with a fixed capacity. Does not unload.
    lsmod_result = subprocess.run(["lsmod"], capture_output=True, text=True)
    if MODULE_NAME in lsmod_result.stdout:
        logger.info(f"Module '{MODULE_NAME}' is already loaded.")
        try:
            dmesg_output = subprocess.run(["dmesg"], capture_output=True, text=True).stdout
            match = None
            for line in reversed(dmesg_output.strip().split('\n')):
                m = re.search(r"rgpio_module:.*base (\d+)", line)
                if m: match = m; break
            if match is None:
                raise Exception("Could not find module base in dmesg. Module might be initializing.")
            base_gpio = int(match.group(1))
            with open(f"/sys/class/gpio/gpiochip{base_gpio}/ngpio", 'r') as f:
                current_capacity = int(f.read().strip())
            trigger_path_base = f"/sys/devices/platform/{MODULE_NAME}"
            if not os.path.exists(os.path.join(trigger_path_base, "trigger_irq")):
                 trigger_path_base = f"/sys/devices/platform/{MODULE_NAME}.0"
            trigger_path = os.path.join(trigger_path_base, "trigger_irq")
            return base_gpio, trigger_path, current_capacity
        except Exception as e:
            logger.critical(f"Could not verify existing module, a reboot may be required. Error: {e}")
            return None, None, 0
    logger.info(f"Module not loaded. Attempting to load with capacity={capacity}...")
    try:
        subprocess.run(["insmod", module_path, f"num_gpios={capacity}"], check=True)
        time.sleep(1)
        return manage_kernel_module(module_path, capacity)
    except Exception as e:
        logger.error(f"Failed to load kernel module: {e}")
        return None, None, 0

def manage_exported_gpios(gpio_base, offsets_to_export, offsets_to_unexport):
    # Exports or unexports specific GPIOs to make them visible in /sys/class/gpio.
    changed = False
    if offsets_to_export:
        logger.info(f"Exporting new GPIOs at offsets: {sorted(list(offsets_to_export))}")
        changed = True
        for offset in sorted(list(offsets_to_export)):
            gpio_num = gpio_base + offset
            try:
                if not os.path.exists(f"/sys/class/gpio/gpio{gpio_num}"):
                    with open("/sys/class/gpio/export", 'w') as f: f.write(str(gpio_num))
                    time.sleep(0.05)
            except Exception as e: logger.warning(f"Could not export GPIO {gpio_num}: {e}")
    if offsets_to_unexport:
        logger.info(f"Unexporting obsolete GPIOs at offsets: {sorted(list(offsets_to_unexport))}")
        changed = True
        for offset in sorted(list(offsets_to_unexport)):
            gpio_num = gpio_base + offset
            try:
                if os.path.exists(f"/sys/class/gpio/gpio{gpio_num}"):
                    with open("/sys/class/gpio/unexport", 'w') as f: f.write(str(gpio_num))
            except Exception as e: logger.warning(f"Could not unexport GPIO {gpio_num}: {e}")
    return changed

def create_io_ext_files(persistent_map, gpio_base, device_configs):
    # Creates the /run/io-ext structure for dbus-digitalinputs discovery.
    logger.info("Rebuilding io-ext configuration files and symlinks...")
    io_ext_dir = "/run/io-ext"
    os.makedirs(io_ext_dir, exist_ok=True)
    
    for cfg in device_configs.values():
        serial_raw = cfg['serial']
        serial_safe = serial_raw.replace('-', '_')
        num_inputs = int(cfg.get('num_inputs', 0))
        num_relays = int(cfg.get('num_relays', 0))
        
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
    # Cleans up GPIOs, D-Bus services, and io-ext files on script exit.
    logger.info("Performing cleanup on exit...")
    
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

    if driver_instance.persistent_map and driver_instance.gpio_base is not None:
        offsets_to_unexport = list(driver_instance.persistent_map.values())
        manage_exported_gpios(driver_instance.gpio_base, [], offsets_to_unexport)
    
    logger.info("Unregistering D-Bus switch services...")
    for service in list(driver_instance.relay_services.values()):
        service.unregister()

# =================================================================
# MAIN DRIVER CLASS
# =================================================================

class RgpioDriver:
    def __init__(self, gpio_base, trigger_path, mapping_path, module_capacity):
        self.gpio_base = gpio_base
        self.trigger_file = trigger_path
        self.mapping_path = mapping_path
        self.module_capacity = module_capacity
        self.client = None
        self.persistent_map = self._load_persistent_map()
        self.relay_services = {}
        self.device_configs = {} # In-memory store of registered devices
        self.active_safe_serials = set()
        self.unregister_queue = []
        self.unregister_timer = None

    def _load_persistent_map(self):
        # ... (Identical) ...
        mapping = {}
        try:
            parser = configparser.ConfigParser(); parser.optionxform = str
            parser.read(self.mapping_path)
            if 'mapping' in parser:
                for key, value in parser['mapping'].items(): mapping[key] = int(value)
        except Exception: logger.warning(f"Could not load mapping file.")
        return mapping

    def _save_persistent_map(self):
        # ... (Identical) ...
        parser = configparser.ConfigParser(); parser.optionxform = str
        parser['mapping'] = {key: str(value) for key, value in self.persistent_map.items()}
        try:
            with open(self.mapping_path, 'w') as f: parser.write(f)
        except Exception as e: logger.error(f"Could not save mapping file: {e}")

    def _get_currently_exported_offsets(self):
        return {i for i in range(self.module_capacity) if os.path.exists(f"/sys/class/gpio/gpio{self.gpio_base + i}")}

    def _reconcile_state(self):
        # This central function reconciles the desired state (from device_configs)
        # with the actual state (sysfs, D-Bus).
        logger.info("Reconciling system state...")
        
        # --- Reconcile Inputs and GPIOs ---
        new_persistent_map = {}
        used_offsets = set(self.persistent_map.values())
        for cfg in self.device_configs.values():
            serial_raw = cfg['serial']
            for i in range(1, int(cfg.get('num_inputs', 0)) + 1):
                unique_id = f"{serial_raw}_input_{i}"
                if unique_id in self.persistent_map:
                    offset = self.persistent_map[unique_id]
                else:
                    offset = 0
                    while offset in used_offsets: offset += 1
                    logger.info(f"Assigning new offset {offset} to {unique_id}")
                    used_offsets.add(offset)
                new_persistent_map[unique_id] = offset
        
        required_offsets = set(new_persistent_map.values())
        exported_offsets = self._get_currently_exported_offsets()
        gpio_state_changed = manage_exported_gpios(self.gpio_base, required_offsets - exported_offsets, exported_offsets - required_offsets)
        
        # --- Reconcile Relay Services ---
        current_safe_serials = {cfg['serial'].replace('-', '_') for cfg in self.device_configs.values()}
        serials_to_remove = self.active_safe_serials - current_safe_serials
        
        if serials_to_remove:
            logger.info(f"Preparing to remove obsolete devices: {list(serials_to_remove)}")
            
            for serial in serials_to_remove:
                device_dir_to_remove = os.path.join("/run/io-ext", serial)
                if os.path.exists(device_dir_to_remove):
                    logger.info(f"Removing obsolete io-ext directory: {device_dir_to_remove}")
                    shutil.rmtree(device_dir_to_remove)
            
            logger.info(f"Restarting '{DBUS_SERVICE_PATH}' to reflect removed inputs.")
            subprocess.run(["svc", "-t", DBUS_SERVICE_PATH])
            
            for serial in serials_to_remove:
                if serial in self.relay_services:
                    logger.info(f"Unregistering D-Bus Switch service for {serial}")
                    self.relay_services[serial].unregister()
                    del self.relay_services[serial]
        
        for cfg in self.device_configs.values():
            serial_safe = cfg['serial'].replace('-', '_')
            if serial_safe not in self.relay_services:
                logger.info(f"Creating new D-Bus Switch service for {cfg['serial']}")
                bus = dbus.SystemBus(private=True)
                self.relay_services[serial_safe] = DbusRgpioSwitchService(cfg, self, bus)
        
        # --- Finalize state ---
        self.persistent_map = new_persistent_map
        self.active_safe_serials = current_safe_serials
        self._save_persistent_map()
        
        create_io_ext_files(self.persistent_map, self.gpio_base, self.device_configs)
        
        if gpio_state_changed:
            logger.info(f"GPIO state changed, restarting '{DBUS_SERVICE_PATH}'...")
            subprocess.run(["svc", "-t", DBUS_SERVICE_PATH])

    def on_api_message(self, client, userdata, msg):
        # Handles all messages from the internal API.
        try:
            topic = msg.topic
            payload = msg.payload.decode()
            parts = topic.split('/')

            if topic.startswith(API_DEVICE_REGISTER_TOPIC):
                serial = parts[-1]
                if payload == "UNREGISTER":
                    logger.info(f"Received un-registration request for device '{serial}'")
                    if serial not in self.unregister_queue:
                        self.unregister_queue.append(serial)
                    if self.unregister_timer is None:
                        logger.info("Starting unregister timer...")
                        self.unregister_timer = GLib.timeout_add(500, self._process_unregister_queue) # 500ms
                else:
                    logger.info(f"Received registration request for device '{serial}'")
                    device_config = json.loads(payload)
                    self.device_configs[serial] = device_config
                    self._reconcile_state()

            elif topic.startswith(API_DEVICE_STATUS_TOPIC):
                serial = parts[-1]
                serial_safe = serial.replace('-', '_')
                if serial_safe in self.relay_services:
                    is_connected = (payload == "CONNECTED")
                    self.relay_services[serial_safe].set_connection_state(is_connected)

            elif topic.startswith(API_INPUT_STATE_TOPIC):
                serial, input_index = parts[4], int(parts[5])
                unique_id = f"{serial}_input_{input_index}"
                if unique_id in self.persistent_map:
                    self._handle_input_state_change(unique_id, payload)
            
            # MODIFIED: More robust check for relay name topic
            elif topic.startswith(API_DEVICE_RELAY_NAME_TOPIC) and len(parts) == 5 and parts[4].startswith("Relay_"):
                try:
                    serial = parts[3]
                    relay_str = parts[4] # e.g., "Relay_3"
                    relay_index = int(relay_str.split('_')[1]) - 1 # convert to 0-based index
                    new_name = payload
                    
                    serial_safe = serial.replace('-', '_')
                    if serial_safe in self.relay_services:
                        self.relay_services[serial_safe].update_relay_name(relay_index, new_name)
                except (IndexError, ValueError) as e:
                    logger.warning(f"Could not parse relay name topic: {topic}. Error: {e}")

        except Exception as e:
            logger.error(f"Error processing API message on topic {msg.topic}: {e}")

    def _process_unregister_queue(self):
        # Process all accumulated unregister requests.
        logger.info(f"Processing unregister queue for devices: {self.unregister_queue}")
        
        for serial in self.unregister_queue:
            if serial in self.device_configs:
                del self.device_configs[serial]
        
        self.unregister_queue = []
        self.unregister_timer = None # Reset timer
        
        self._reconcile_state()
        
        return False # Stop the timer

    def _handle_input_state_change(self, unique_id, payload):
        # Triggers the virtual GPIO for a given input.
        offset = self.persistent_map.get(unique_id)
        if offset is None: return
        try:
            gpio_num = self.gpio_base + offset
            with open(f"/sys/class/gpio/gpio{gpio_num}/direction", 'w') as f: f.write('out')
            with open(f"/sys/class/gpio/gpio{gpio_num}/value", 'w') as f: f.write(payload)
            with open(f"/sys/class/gpio/gpio{gpio_num}/direction", 'w') as f: f.write('in')
            with open(self.trigger_file, "w") as f: f.write(str(offset))
        except Exception as e:
            logger.error(f"Error processing input state for {unique_id}: {e}")

    def publish_relay_command(self, serial, index, state):
        # Publishes a relay command to the internal API.
        if self.client and self.client.is_connected():
            payload = "ON" if state == 1 else "OFF"
            command_topic = f"{API_RELAY_SET_TOPIC}/{serial}/{index+1}"
            self.client.publish(command_topic, payload)
            logger.info(f"Published API command: Topic={command_topic}, Payload={payload}")

    def start(self):
        # Starts the internal API MQTT client.
        self.client = mqtt.Client(**MQTT_CLIENT_ARGS)
        self.client.on_message = self.on_api_message
        self.client.connect("localhost", 1883, 60)
        self.client.subscribe(f"{API_INPUT_STATE_TOPIC}/#")
        self.client.subscribe(f"{API_DEVICE_REGISTER_TOPIC}/#")
        self.client.subscribe(f"{API_DEVICE_STATUS_TOPIC}/#")
        # MODIFIED: Use a valid wildcard subscription
        self.client.subscribe(f"{API_DEVICE_RELAY_NAME_TOPIC}/+/+")
        self.client.loop_start()
        logger.info("Internal API MQTT bridge started.")

    def stop(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("Internal API MQTT bridge stopped.")

# =================================================================
# D-BUS SERVICE CLASS for a SINGLE RELAY DEVICE
# =================================================================

class DbusRgpioSwitchService:
    def __init__(self, device_config, parent_driver, bus):
        self.config = device_config
        self.parent_driver = parent_driver
        self.bus = bus
        self.serial = self.config.get('serial', 'RGPIO-IO-???')
        serial_safe = self.serial.replace('-', '_')
        self.servicename = f'com.victronenergy.switch.{serial_safe}'
        self._dbusservice = VeDbusService(self.servicename, bus=self.bus, register=False)
        self._settings = self._setup_settings()

        self._dbusservice.add_path('/Management/ProcessName', __file__)
        self._dbusservice.add_path('/Management/ProcessVersion', '3.4.1 (dbus-rgpio)')
        self._dbusservice.add_path('/Management/Connection', 'RGPIO Core Service')
        self._dbusservice.add_path('/DeviceInstance', int(self.config.get('device_instance', 50)))
        self._dbusservice.add_path('/ProductId', 19191)
        self._dbusservice.add_path('/ProductName', 'RemoteGPIO')
        self._dbusservice.add_path('/FirmwareVersion', '3.4.1')
        self._dbusservice.add_path('/HardwareVersion', 'N/A')
        self._dbusservice.add_path('/Connected', 1)
        self._dbusservice.add_path('/Serial', self.serial)
        self._dbusservice.add_path('/State', 256)

        self._dbusservice.add_path(
            path='/CustomName',
            value=self._settings['CustomName'],
            writeable=True,
            onchangecallback=lambda p, v: self._handle_writable_setting_change('CustomName', p, v)
        )
        
        for i in range(int(self.config.get('num_relays', 0))):
            self._create_relay_paths(i)
            
        self._dbusservice.register()

    def _setup_settings(self):
        serial_safe = self.serial.replace('-', '_')
        settings_id = f"switch_{serial_safe}"
        settings_path_prefix = f'/Settings/Devices/{settings_id}'
        supported_settings = {'CustomName': [f'{settings_path_prefix}/CustomName', f'RGPIO Module ({self.serial})', 0, 0]}
        for i in range(int(self.config.get('num_relays', 0))):
            relay_id = i + 1
            supported_settings[f'Relay{relay_id}State'] = [f'{settings_path_prefix}/Relay/{relay_id}/State', 0, 0, 1]
            supported_settings[f'Relay{relay_id}CustomName'] = [f'{settings_path_prefix}/Relay/{relay_id}/CustomName', '', 0, 0]
            supported_settings[f'Relay{relay_id}Function'] = [f'{settings_path_prefix}/Relay/{relay_id}/Function', 2, 0, 0]
            supported_settings[f'Relay{relay_id}Group'] = [f'{settings_path_prefix}/Relay/{relay_id}/Group', '', 0, 0]
            supported_settings[f'Relay{relay_id}ShowUIControl'] = [f'{settings_path_prefix}/Relay/{relay_id}/ShowUIControl', 1, 0, 1]
            supported_settings[f'Relay{relay_id}Type'] = [f'{settings_path_prefix}/Relay/{relay_id}/Type', 1, 0, 0]
        return SettingsDevice(self._dbusservice._dbusconn, supported_settings, None)

    def _create_relay_paths(self, relay_index):
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
        self._settings[settings_dict_key] = value
        return True

    def _handle_relay_state_change(self, index, path, value):
        self._settings[f'Relay{index+1}State'] = value
        self.parent_driver.publish_relay_command(self.serial, index, value)
        return True
    
    def set_connection_state(self, is_connected):
        if is_connected:
            self._dbusservice['/Connected'] = 1
            self._dbusservice['/State'] = 256
        else:
            self._dbusservice['/Connected'] = 0
            self._dbusservice['/State'] = 259
            logger.warning(f"Device {self.serial} marked as disconnected.")

    def update_relay_name(self, relay_index, new_name):
        # NEW: Method to update a relay's custom name via API
        relay_id = relay_index + 1
        logger.info(f"Updating name for relay {relay_id} of {self.serial} to '{new_name}'")
        dbus_path = f'/SwitchableOutput/relay_{relay_id}/Settings/CustomName'
        self._dbusservice[dbus_path] = new_name

    def unregister(self):
        try:
            if self.bus: self.bus.close()
        except Exception as e: logger.error(f"Error unregistering service {self.servicename}: {e}")

if __name__ == "__main__":
    DBusGMainLoop(set_as_default=True)
    logger.info("--- Starting RGPIO Unified Driver Engine ---")
    
    gpio_base_num, trigger_path, module_capacity = manage_kernel_module(
        module_path=MODULE_PATH, capacity=MODULE_CAPACITY)
    
    if gpio_base_num is None: sys.exit(1)
    
    driver = RgpioDriver(
        gpio_base=gpio_base_num, 
        trigger_path=trigger_path, 
        mapping_path=MAPPING_FILE,
        module_capacity=module_capacity
    )
    
    def shutdown_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully.")
        driver.stop()
        cleanup_on_exit(driver)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    driver.start()
    
    mainloop = GLib.MainLoop()
    
    def publish_heartbeat(driver_instance):
        if driver_instance and driver_instance.client and driver_instance.client.is_connected():
            driver_instance.client.publish(API_HEARTBEAT_TOPIC, str(int(time.time())), retain=True)
        return True

    GLib.timeout_add_seconds(10, publish_heartbeat, driver)
    
    try:
        mainloop.run()
    except Exception as e:
        logger.error(f"An unexpected error occurred in the main loop: {e}")
    finally:
        if driver and driver.client and driver.client.is_connected():
            driver.client.publish(API_HEARTBEAT_TOPIC, "", retain=True)
        driver.stop()
        cleanup_on_exit(driver)
        logger.info("--- RGPIO Unified Driver Engine stopped ---")

