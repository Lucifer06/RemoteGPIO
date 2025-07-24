#!/usr/bin/env python3

import configparser
import paho.mqtt.client as mqtt
import os
import sys
import logging
import time
import subprocess
import re
import shutil

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

def cleanup_on_exit(active_serials, persistent_map, gpio_base):
    """Unexports all used GPIOs and cleans up our io-ext files on exit."""
    logger.info("Performing cleanup on exit...")
    
    if persistent_map and gpio_base is not None:
        offsets_to_unexport = list(persistent_map.values())
        manage_exported_gpios(gpio_base, [], offsets_to_unexport)
    
    io_ext_dir = "/run/io-ext"
    try:
        for serial_safe in active_serials:
            device_dir = os.path.join(io_ext_dir, serial_safe)
            if os.path.exists(device_dir):
                logger.info(f"  - Removing {device_dir}")
                shutil.rmtree(device_dir)
        
        if os.path.exists(io_ext_dir) and not os.listdir(io_ext_dir):
            logger.info(f"  - Removing empty parent directory {io_ext_dir}")
            os.rmdir(io_ext_dir)
    except Exception as e:
        logger.error(f"Error during io-ext cleanup: {e}")

class GpioBridge:
    def __init__(self, gpio_base, trigger_path, config_path, mapping_path, module_capacity):
        self.gpio_base = gpio_base
        self.trigger_file = trigger_path
        self.config_path = config_path
        self.mapping_path = mapping_path
        self.module_capacity = module_capacity
        self.client = None
        self.mqtt_to_gpio_map = {}
        self.persistent_map = self._load_persistent_map()
        self.active_safe_serials = set() # Track dirs we manage
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

        # --- Update Persistent Mapping ---
        old_offsets = set(self.persistent_map.values())
        new_persistent_map = {}
        new_mqtt_to_gpio_map = {}
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
                new_mqtt_to_gpio_map[f"{topic_base}/input/{i}"] = offset
        
        new_offsets = set(new_persistent_map.values())
        offsets_to_export = new_offsets - old_offsets
        offsets_to_unexport = old_offsets - new_offsets
        
        # --- Update System State ---
        gpio_state_changed = manage_exported_gpios(self.gpio_base, offsets_to_export, offsets_to_unexport)

        # --- Update io-ext Safely ---
        io_ext_dir = "/run/io-ext"
        os.makedirs(io_ext_dir, exist_ok=True)
        new_safe_serials = {d['serial'].replace('-', '_') for d in device_configs.values()}
        serials_to_remove = self.active_safe_serials - new_safe_serials
        for serial in serials_to_remove:
            shutil.rmtree(os.path.join(io_ext_dir, serial), ignore_errors=True)

        for cfg in device_configs.values():
            serial_raw = cfg['serial']
            serial_safe = serial_raw.replace('-', '_')
            device_dir = f"{io_ext_dir}/{serial_safe}"
            os.makedirs(device_dir, exist_ok=True)
            pins_content = [f"tag\t{serial_safe}"]
            for i in range(1, int(cfg.get('num_inputs', 0)) + 1):
                pins_content.append(f"input\t{device_dir}/input_{i} {i}")
                unique_id = f"{serial_raw}_input_{i}"
                if unique_id in new_persistent_map:
                    offset = new_persistent_map[unique_id]
                    link_target = f"/sys/class/gpio/gpio{self.gpio_base + offset}"
                    link_path = os.path.join(device_dir, f"input_{i}")
                    if os.path.lexists(link_path): os.remove(link_path)
                    os.symlink(link_target, link_path)
            for i in range(1, int(cfg.get('num_relays', 0)) + 1):
                pins_content.append(f"relay\t{device_dir}/relay_{i} {i}")
            with open(os.path.join(device_dir, "pins.conf"), 'w') as f:
                f.write("\n".join(pins_content) + "\n")
        
        # --- Update Internal State ---
        self.persistent_map = new_persistent_map
        old_topics = set(self.mqtt_to_gpio_map.keys())
        self.mqtt_to_gpio_map = new_mqtt_to_gpio_map
        new_topics = set(self.mqtt_to_gpio_map.keys())
        self.active_safe_serials = new_safe_serials

        # --- Update MQTT Subscriptions ---
        if self.client and self.client.is_connected():
            if old_topics - new_topics: self.client.unsubscribe(list(old_topics - new_topics))
            if new_topics - old_topics: self.client.subscribe([(t, 0) for t in new_topics - old_topics])
        
        self._save_persistent_map()
        
        # --- Restart Victron Service if Needed ---
        if gpio_state_changed:
            logger.info(f"GPIO state changed, restarting '{DBUS_SERVICE_PATH}'...")
            subprocess.run(["svc", "-t", DBUS_SERVICE_PATH])

        logger.info(f"Reconfiguration complete. Now monitoring {len(self.mqtt_to_gpio_map)} inputs.")

    def on_mqtt_message(self, client, userdata, msg):
        virtual_line = self.mqtt_to_gpio_map.get(msg.topic)
        if virtual_line is None: return
        try:
            gpio_num = self.gpio_base + virtual_line
            with open(f"/sys/class/gpio/gpio{gpio_num}/direction", 'w') as f: f.write('out')
            with open(f"/sys/class/gpio/gpio{gpio_num}/value", 'w') as f: f.write(msg.payload.decode())
            with open(f"/sys/class/gpio/gpio{gpio_num}/direction", 'w') as f: f.write('in')
            with open(self.trigger_file, "w") as f: f.write(str(virtual_line))
        except Exception as e:
            logger.error(f"Error processing message for {msg.topic}: {e}")

    def start(self):
        config = configparser.ConfigParser()
        config.read(self.config_path)
        broker_config = config['mqtt_broker']
        
        self.client = mqtt.Client(1)
        self.client.on_message = self.on_mqtt_message
        
        if broker_config.get('username'):
            self.client.username_pw_set(broker_config['username'], broker_config.get('password'))
        
        self.client.connect(broker_config['address'], int(broker_config['port']), 60)
        
        for topic in self.mqtt_to_gpio_map.keys():
            self.client.subscribe(topic)
        
        self.client.loop_start()
        logger.info("MQTT bridge started in background.")

    def stop(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT bridge stopped.")

if __name__ == "__main__":
    logger.info("--- Starting rgpio driver for virtual inputs ---")
    
    gpio_base_num, trigger_path, module_capacity = manage_kernel_module(
        module_path=MODULE_PATH, capacity=MODULE_CAPACITY)
    
    if gpio_base_num is None:
        logger.critical("Could not configure kernel module. The script will exit.")
        sys.exit(1)
    
    bridge = GpioBridge(
        gpio_base=gpio_base_num, 
        trigger_path=trigger_path, 
        config_path=CONFIG_FILE,
        mapping_path=MAPPING_FILE,
        module_capacity=module_capacity
    )
    bridge.start()

    last_config_mtime = os.path.getmtime(CONFIG_FILE)

    try:
        while True:
            time.sleep(CONFIG_CHECK_INTERVAL)
            try:
                current_mtime = os.path.getmtime(CONFIG_FILE)
                if current_mtime != last_config_mtime:
                    logger.info("Configuration file change detected.")
                    last_config_mtime = current_mtime
                    bridge.reconfigure()
            except FileNotFoundError:
                logger.warning(f"Configuration file '{CONFIG_FILE}' not found. Skipping check.")
    except KeyboardInterrupt:
        logger.info("Script shutdown requested by user.")
    finally:
        bridge.stop()
        cleanup_on_exit(
            active_serials=bridge.active_safe_serials,
            persistent_map=bridge.persistent_map, 
            gpio_base=gpio_base_num
        )
        logger.info("--- rgpio driver stopped ---")

