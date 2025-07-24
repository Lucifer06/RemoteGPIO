#!/usr/bin/env python3

import configparser
import paho.mqtt.client as mqtt
import os
import sys
import logging
import time
import subprocess
import re

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RgpioDriver")

# --- CONSTANTS ---
CONFIG_FILE = '/data/RemoteGPIO/conf/config.ini'
MODULE_NAME = 'rgpio_module'
MODULE_PATH = f'/data/RemoteGPIO/{MODULE_NAME}.ko' # Path to your .ko module
MIN_GPIOS = 8 # Minimum number of GPIOs to create, even if config is empty
DBUS_SERVICE_PATH = '/service/dbus-digitalinputs' # Path to the dependent service

def export_gpios(gpio_base, count):
    """
    Programmatically exports the virtual GPIO lines to make them visible in /sys/class/gpio.
    """
    logger.info(f"Exporting {count} GPIO lines starting from base {gpio_base}...")
    export_path = "/sys/class/gpio/export"
    if not os.path.exists(export_path):
        logger.error(f"GPIO export path not found: {export_path}. Cannot proceed.")
        return False
        
    for i in range(count):
        gpio_num = gpio_base + i
        gpio_dir = f"/sys/class/gpio/gpio{gpio_num}"
        if not os.path.exists(gpio_dir):
            try:
                with open(export_path, 'w') as f:
                    f.write(str(gpio_num))
                logger.info(f"  - Exported GPIO {gpio_num}")
                # A short delay might be needed for sysfs to catch up
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"  - Failed to export GPIO {gpio_num}: {e}")
                # Continue anyway, maybe it was just created
        else:
            logger.info(f"  - GPIO {gpio_num} already exported.")
    return True

def manage_kernel_module(config_path, module_path):
    """
    Manages the kernel module lifecycle:
    1. Calculate the total number of required GPIOs from the config.
    2. Unload the old module instance.
    3. Load the new instance with the correct number of GPIOs.
    4. Retrieve the GPIO base number and the trigger file path.
    Returns a tuple (base_gpio, trigger_path, total_inputs) on success, otherwise (None, None, 0).
    """
    # 1. Calculate the required number of GPIOs
    total_inputs = 0
    try:
        config = configparser.ConfigParser()
        config.read(config_path)
        for section in config.sections():
            if section.startswith('device_'):
                total_inputs += int(config[section].get('num_inputs', 0))
    except Exception as e:
        logger.error(f"Error while reading the configuration file: {e}")
        return None, None, 0

    if total_inputs == 0:
        logger.warning(f"No inputs configured, creating the minimum number of GPIOs: {MIN_GPIOS}")
        total_inputs = MIN_GPIOS
    
    logger.info(f"Total number of required inputs: {total_inputs}")

    # 2. Unload the module if it's already loaded
    logger.info(f"Attempting to unload module '{MODULE_NAME}'...")
    subprocess.run(["rmmod", MODULE_NAME], capture_output=True)
    time.sleep(0.5) # Short pause to let the system stabilize

    # 3. Load the module with the correct parameter
    logger.info(f"Loading module '{MODULE_NAME}' with num_gpios={total_inputs}...")
    try:
        if not os.path.exists(module_path):
            logger.error(f"Kernel module file not found: {module_path}")
            return None, None, 0
        
        cmd = ["insmod", module_path, f"num_gpios={total_inputs}"]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to load kernel module: {e.stderr.strip()}")
        return None, None, 0
    
    logger.info("Kernel module loaded successfully.")
    time.sleep(0.5) # Pause before reading dmesg

    # 4. Retrieve GPIO base number and trigger path
    base_gpio = None
    trigger_path = None
    
    # Retrieve GPIO base from dmesg
    try:
        dmesg_output = subprocess.run(["dmesg"], capture_output=True, text=True).stdout
        match = None
        # We look for the last occurrence
        for line in reversed(dmesg_output.strip().split('\n')):
            m = re.search(r"rgpio_module:.*base (\d+)", line)
            if m:
                match = m
                break
        
        if match:
            base_gpio = int(match.group(1))
            logger.info(f"GPIO base number found: {base_gpio}")
        else:
            logger.error("Could not find GPIO base number in dmesg.")
            return None, None, total_inputs
    except Exception as e:
        logger.error(f"Error while parsing dmesg: {e}")
        return None, None, total_inputs

    # Dynamically find the trigger file path
    try:
        # The device is created under /sys/devices/platform/
        platform_dev_path = f"/sys/devices/platform/{MODULE_NAME}.0"
        if not os.path.isdir(platform_dev_path):
             # Fallback if .0 is not appended
            platform_dev_path = f"/sys/devices/platform/{MODULE_NAME}"

        path_to_check = os.path.join(platform_dev_path, "trigger_irq")

        if os.path.exists(path_to_check):
            trigger_path = path_to_check
            logger.info(f"Trigger file found at: {trigger_path}")
        else:
            logger.error(f"Checked {path_to_check}, but trigger file is not found.")
            return base_gpio, None, total_inputs

    except Exception as e:
        logger.error(f"Error while searching for trigger file: {e}")
        return base_gpio, None, total_inputs

    return base_gpio, trigger_path, total_inputs

def create_io_ext_files(config_path, gpio_base):
    """
    Creates the /run/io-ext directory structure, pins.conf files,
    and input symlinks for each device defined in the configuration.
    """
    logger.info("Creating io-ext configuration files and symlinks...")
    virtual_gpio_offset = 0
    try:
        config = configparser.ConfigParser()
        config.read(config_path)
        for section in config.sections():
            if section.startswith('device_'):
                serial = config[section].get('serial')
                num_inputs = int(config[section].get('num_inputs', 0))
                num_relays = int(config[section].get('num_relays', 0))

                if not serial:
                    logger.warning(f"Skipping section {section} due to missing 'serial' key.")
                    continue
                
                logger.info(f"Processing device {serial} for io-ext...")

                # Create device directory
                device_dir = f"/run/io-ext/{serial}"
                os.makedirs(device_dir, exist_ok=True)
                
                # Build pins.conf content
                pins_content = []
                pins_content.append(f"tag\t{serial}")
                
                for i in range(1, num_inputs + 1):
                    pins_content.append(f"input\t/run/io-ext/{serial}/input_{i} {i}")

                    # Create symbolic link for the input
                    gpio_num = gpio_base + virtual_gpio_offset
                    link_target = f"/sys/class/gpio/gpio{gpio_num}"
                    link_path = os.path.join(device_dir, f"input_{i}")

                    if os.path.lexists(link_path): # Use lexists for symlinks
                        os.remove(link_path)
                    
                    os.symlink(link_target, link_path)
                    logger.info(f"  - Created symlink: {link_path} -> {link_target}")
                    
                    virtual_gpio_offset += 1 # Increment offset for each input
                
                for i in range(1, num_relays + 1):
                    pins_content.append(f"relay\t/run/io-ext/{serial}/relay_{i} {i}")
                
                # Write pins.conf file
                pins_conf_path = os.path.join(device_dir, "pins.conf")
                with open(pins_conf_path, 'w') as f:
                    f.write("\n".join(pins_content) + "\n")
                
                logger.info(f"Successfully created {pins_conf_path}")

    except Exception as e:
        logger.error(f"Failed to create io-ext files: {e}")

class GpioBridge:
    def __init__(self, gpio_base, trigger_path, config_path):
        self.gpio_base = gpio_base
        self.trigger_file = trigger_path
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.mqtt_to_gpio_map = {}
        self.virtual_gpio_offset = 0
        self.setup_device_mappings()

    def setup_device_mappings(self):
        logger.info("Configuring MQTT -> GPIO mappings...")
        for section in self.config.sections():
            if section.startswith('device_'):
                try:
                    topic_base = self.config[section]['topic_base']
                    num_inputs = int(self.config[section]['num_inputs'])
                    logger.info(f"Device {section}: {num_inputs} inputs, base topic {topic_base}")
                    for i in range(num_inputs):
                        mqtt_topic = f"{topic_base}/input/{i + 1}"
                        virtual_line = self.virtual_gpio_offset
                        self.mqtt_to_gpio_map[mqtt_topic] = virtual_line
                        logger.info(f"  - Mapping: {mqtt_topic} -> Virtual line {virtual_line} (GPIO {self.gpio_base + virtual_line})")
                        self.virtual_gpio_offset += 1
                except (KeyError, ValueError) as e:
                    logger.error(f"Configuration error in section {section}: {e}")
        logger.info(f"Mapping finished. {len(self.mqtt_to_gpio_map)} total inputs.")

    def on_mqtt_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        logger.debug(f"Message received - Topic: {topic}, Payload: {payload}")
        virtual_line = self.mqtt_to_gpio_map.get(topic)
        if virtual_line is None:
            return
        try:
            gpio_num = self.gpio_base + virtual_line
            gpio_value_path = f"/sys/class/gpio/gpio{gpio_num}/value"
            gpio_direction_path = f"/sys/class/gpio/gpio{gpio_num}/direction"
            with open(gpio_direction_path, 'w') as f:
                f.write('out')
            with open(gpio_value_path, 'w') as f:
                f.write(payload)
            with open(gpio_direction_path, 'w') as f:
                f.write('in')
            with open(self.trigger_file, "w") as f:
                f.write(str(virtual_line))
        except Exception as e:
            logger.error(f"Error while processing message for {topic}: {e}")

    def start(self):
        broker_config = self.config['mqtt_broker']
        client = mqtt.Client(1)
        client.on_message = self.on_mqtt_message
        if broker_config.get('username'):
            client.username_pw_set(broker_config['username'], broker_config.get('password'))
        logger.info(f"Connecting to MQTT broker at {broker_config['address']}:{broker_config['port']}")
        client.connect(broker_config['address'], int(broker_config['port']), 60)
        for topic in self.mqtt_to_gpio_map.keys():
            logger.info(f"Subscribing to {topic}")
            client.subscribe(topic)
        logger.info("MQTT to rgpio bridge started. Waiting for messages...")
        client.loop_forever()

if __name__ == "__main__":
    logger.info("--- Starting rgpio driver for virtual inputs ---")
    
    try:
        # Stop dependent services before managing kernel modules
        if os.path.exists(DBUS_SERVICE_PATH):
            logger.info(f"Stopping dependent service: {DBUS_SERVICE_PATH}")
            subprocess.run(["svc", "-d", DBUS_SERVICE_PATH], capture_output=True)
            time.sleep(1) # Give the service time to stop

        # Step 1: Manage kernel module
        gpio_base_num, trigger_path, total_inputs_count = manage_kernel_module(
            config_path=CONFIG_FILE, module_path=MODULE_PATH)
        
        if gpio_base_num is None or trigger_path is None:
            logger.critical("Could not configure kernel module. The script will exit.")
            sys.exit(1) # The finally block will handle the restart
        
        # Step 2: Export GPIOs
        if not export_gpios(gpio_base=gpio_base_num, count=total_inputs_count):
            logger.critical("Failed to export GPIOs. The script will exit.")
            sys.exit(1) # The finally block will handle the restart

        # Step 3: Create io-ext files
        create_io_ext_files(config_path=CONFIG_FILE, gpio_base=gpio_base_num)
            
        # Step 4: Restart the service now that setup is complete
        if os.path.exists(DBUS_SERVICE_PATH):
            logger.info(f"Restarting dependent service: {DBUS_SERVICE_PATH}")
            subprocess.run(["svc", "-u", DBUS_SERVICE_PATH])

        # Step 5: Start the MQTT bridge
        bridge = GpioBridge(gpio_base=gpio_base_num, trigger_path=trigger_path, config_path=CONFIG_FILE)
        bridge.start()

    except KeyboardInterrupt:
        logger.info("Script shutdown requested by user.")
    except Exception as e:
        logger.critical(f"A fatal error occurred: {e}")
    finally:
        # Ensure the dependent service is running when this script exits, for any reason.
        if os.path.exists(DBUS_SERVICE_PATH):
            logger.info(f"Ensuring dependent service '{DBUS_SERVICE_PATH}' is running on exit.")
            subprocess.run(["svc", "-u", DBUS_SERVICE_PATH])
        logger.info("--- rgpio driver stopped ---")

