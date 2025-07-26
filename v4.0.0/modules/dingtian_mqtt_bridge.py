#!/usr/bin/env python3

# #############################################################################
#
#   dingtian_mqtt_bridge.py
#
#   A communication module for Dingtian devices.
#   - Reads its own configuration for Dingtian-specific details.
#   - Connects to the Dingtian MQTT topics.
#   - Acts as a bridge to the dbus-rgpio.py engine via an internal API.
#   - Retries loading configuration if it's invalid or missing.
#
# #############################################################################

import configparser
import paho.mqtt.client as mqtt
import os
import sys
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DingtianBridge")

# --- CONSTANTS ---
# MODIFIED: Updated config file name
CONFIG_FILE = '/data/RemoteGPIO/conf/dingtian_mqtt.ini'
API_TOPIC_BASE = "rgpio/api"
API_INPUT_STATE_TOPIC = f"{API_TOPIC_BASE}/input/state"
API_RELAY_SET_TOPIC = f"{API_TOPIC_BASE}/relay/set"
CONFIG_CHECK_INTERVAL = 10 # Seconds

class DingtianBridge:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self.device_configs = {}
        self.is_configured = False # Flag to check if config is valid
        self.is_started = False # Flag to track if clients are running
        
        self.api_client = mqtt.Client(1)
        self.api_client.on_connect = self.on_api_connect
        self.api_client.on_message = self.on_api_message
        
        self.hardware_client = mqtt.Client(1)
        self.hardware_client.on_connect = self.on_hardware_connect
        self.hardware_client.on_message = self.on_hardware_message
        
        self.reconfigure()

    def reconfigure(self):
        logger.info("Loading Dingtian configuration...")
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Configuration file not found: {self.config_path}. Will retry.")
                self.is_configured = False
                return

            self.config.read(self.config_path)
            
            if 'mqtt_broker' not in self.config:
                logger.error(f"Missing [mqtt_broker] section in {self.config_path}. Will retry.")
                self.is_configured = False
                return
        except Exception as e:
            logger.error(f"Error reading configuration file: {e}. Will retry.")
            self.is_configured = False
            return

        new_device_configs = {}
        for section in self.config.sections():
            if section.startswith('device_'):
                new_device_configs[section] = dict(self.config[section])
        
        self.device_configs = new_device_configs
        self.is_configured = True # Configuration is now valid
        logger.info(f"Found {len(self.device_configs)} Dingtian devices in configuration.")

        # Reconnect hardware client if it's already running
        if self.is_started and self.hardware_client.is_connected():
            self.hardware_client.disconnect()
            self.start_hardware_client()

    def start(self):
        if not self.is_configured:
            logger.error("Cannot start bridge, configuration is invalid.")
            return

        if self.is_started:
            return

        logger.info("Starting Dingtian Bridge clients...")
        self.api_client.connect("localhost", 1883, 60)
        self.api_client.loop_start()
        self.start_hardware_client()
        self.is_started = True

    def start_hardware_client(self):
        broker_cfg = self.config['mqtt_broker']
        address = broker_cfg.get('address', 'localhost')
        port = int(broker_cfg.get('port', 1883))
        
        if broker_cfg.get('username'):
            self.hardware_client.username_pw_set(broker_cfg.get('username'), broker_cfg.get('password'))
            
        logger.info(f"Connecting to Dingtian hardware broker at {address}:{port}")
        self.hardware_client.connect(address, port, 60)
        self.hardware_client.loop_start()

    def on_api_connect(self, client, userdata, flags, rc):
        logger.info("Connected to internal API (dbus-rgpio).")
        client.subscribe(f"{API_RELAY_SET_TOPIC}/#")

    def on_hardware_connect(self, client, userdata, flags, rc):
        logger.info("Connected to Dingtian hardware broker.")
        for cfg in self.device_configs.values():
            topic_base = cfg['topic_base']
            client.subscribe(f"{topic_base}/input/#")
            client.subscribe(f"{topic_base}/relay/+/state")

    def on_api_message(self, client, userdata, msg):
        """ Handles a command from the core engine to set a relay state. """
        try:
            parts = msg.topic.split('/')
            if len(parts) == 6 and parts[3] == 'set': # Corrected part count
                serial = parts[4]
                relay_index = int(parts[5])
                payload = msg.payload.decode() # ON or OFF

                for cfg in self.device_configs.values():
                    if cfg['serial'] == serial:
                        topic_base = cfg['topic_base']
                        # Dingtian relay index is 0-based for MQTT topic
                        hardware_topic = f"{topic_base}/relay/{relay_index-1}/set"
                        logger.info(f"Forwarding command to hardware: {hardware_topic} -> {payload}")
                        self.hardware_client.publish(hardware_topic, payload)
                        break
        except Exception as e:
            logger.error(f"Error processing API message: {e}")

    def on_hardware_message(self, client, userdata, msg):
        """ Handles a state update from the Dingtian hardware. """
        try:
            parts = msg.topic.split('/')
            topic_base = f"{parts[0]}/{parts[1]}"
            
            serial = None
            for cfg in self.device_configs.values():
                if cfg['topic_base'] == topic_base:
                    serial = cfg['serial']
                    break
            if not serial: return

            if len(parts) == 4 and parts[2] == 'input':
                input_index = parts[3]
                payload = msg.payload.decode()
                api_topic = f"{API_INPUT_STATE_TOPIC}/{serial}/{input_index}"
                logger.info(f"Forwarding input state to API: {api_topic} -> {payload}")
                self.api_client.publish(api_topic, payload)

        except Exception as e:
            logger.error(f"Error processing hardware message: {e}")

    def stop(self):
        self.api_client.loop_stop()
        self.api_client.disconnect()
        self.hardware_client.loop_stop()
        self.hardware_client.disconnect()
        logger.info("Dingtian Bridge stopped.")

if __name__ == "__main__":
    bridge = DingtianBridge(CONFIG_FILE)
    
    if bridge.is_configured:
        bridge.start()
        
        last_mtime = os.path.getmtime(CONFIG_FILE)
        try:
            while True:
                time.sleep(10)
                current_mtime = os.path.getmtime(CONFIG_FILE)
                if current_mtime != last_mtime:
                    logger.info("Dingtian config file changed, reconfiguring...")
                    last_mtime = current_mtime
                    bridge.reconfigure()
        except KeyboardInterrupt:
            logger.info("Shutdown requested.")
        finally:
            bridge.stop()
    else:
        logger.critical("Bridge is not configured. The script will now stop.")


