#!/usr/bin/env python3

# #############################################################################
#
#   dingtian_mqtt_bridge.py
#
#   Version: 2.7.0
#
#   Communication module for Dingtian devices. Discovers devices from its
#   config and registers/unregisters them with the core engine.
#
# #############################################################################

import configparser
import paho.mqtt.client as mqtt
import os
import sys
import logging
import time
import json
import signal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DingtianBridge")

# --- CONSTANTS ---
BRIDGE_CONFIG_FILE = '/data/RemoteGPIO/conf/dingtian_mqtt.ini'
API_TOPIC_BASE = "rgpio/api"
API_INPUT_STATE_TOPIC = f"{API_TOPIC_BASE}/input/state"
API_RELAY_SET_TOPIC = f"{API_TOPIC_BASE}/relay/set"
API_DEVICE_REGISTER_TOPIC = f"{API_TOPIC_BASE}/device/register"
API_DEVICE_STATUS_TOPIC = f"{API_TOPIC_BASE}/device/status"
CONFIG_CHECK_INTERVAL = 10

# --- MQTT Client Compatibility ---
try:
    from paho.mqtt.enums import CallbackAPIVersion
    MQTT_CLIENT_ARGS = {'callback_api_version': CallbackAPIVersion.VERSION1}
    logger.info("Configured for paho-mqtt v2.x")
except ImportError:
    MQTT_CLIENT_ARGS = {}
    logger.info("Configured for paho-mqtt v1.x")

class DingtianBridge:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = None # Will be initialized in reconfigure
        self.device_configs = {}
        self.is_configured = False
        self.is_started = False
        
        self.api_client = mqtt.Client(**MQTT_CLIENT_ARGS)
        self.api_client.on_connect = self.on_api_connect
        self.api_client.on_message = self.on_api_message
        self.api_client.on_disconnect = self.on_api_disconnect
        
        self.hardware_client = mqtt.Client(**MQTT_CLIENT_ARGS)
        self.hardware_client.on_connect = self.on_hardware_connect
        self.hardware_client.on_message = self.on_hardware_message
        self.hardware_client.on_disconnect = self.on_hardware_disconnect
        
        self.reconfigure()

    def reconfigure(self):
        logger.info(f"Loading Dingtian configuration from {self.config_path}...")
        
        self.config = configparser.ConfigParser()
        self.config.optionxform = str

        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Configuration file not found. Will retry.")
                self.is_configured = False
                return

            self.config.read(self.config_path)
            if 'mqtt_broker' not in self.config:
                logger.error(f"Missing [mqtt_broker] section. Will retry.")
                self.is_configured = False
                return
        except Exception as e:
            logger.error(f"Error reading configuration file: {e}. Will retry.")
            self.is_configured = False
            return

        old_device_configs = self.device_configs
        new_device_configs = {}
        for section in self.config.sections():
            if section.startswith('device_'):
                if 'serial' in self.config[section]:
                    new_device_configs[section] = dict(self.config[section])
        
        self.device_configs = new_device_configs
        self.is_configured = True
        logger.info(f"Configuration loaded successfully. Found {len(self.device_configs)} devices.")
        
        self.register_devices_with_engine(new_device_configs, old_device_configs)

        if self.is_started:
            if self.hardware_client.is_connected():
                self.hardware_client.disconnect()
            self.start_hardware_client()

    def register_devices_with_engine(self, new_configs_dict, old_configs_dict):
        # Sends register/unregister messages to the core engine.
        if not self.api_client.is_connected():
            logger.warning("API client not connected, cannot register devices yet.")
            return

        new_serials = {cfg['serial'] for cfg in new_configs_dict.values()}
        old_serials = {cfg['serial'] for cfg in old_configs_dict.values()}

        # Unregister devices that have been removed from the config
        for serial in old_serials - new_serials:
            self._unregister_device(serial)
        
        # Register new devices
        for serial in new_serials - old_serials:
            cfg = next((c for c in new_configs_dict.values() if c['serial'] == serial), None)
            if cfg:
                self._register_device(cfg)

    def _register_device(self, cfg):
        serial = cfg['serial']
        logger.info(f"Registering device '{serial}' with core engine.")
        self.api_client.publish(f"{API_DEVICE_REGISTER_TOPIC}/{serial}", json.dumps(cfg), retain=True)
        self.api_client.publish(f"{API_DEVICE_STATUS_TOPIC}/{serial}", "CONNECTED", retain=True)

    def _unregister_device(self, serial):
        logger.info(f"Un-registering device '{serial}' with core engine.")
        self.api_client.publish(f"{API_DEVICE_REGISTER_TOPIC}/{serial}", "UNREGISTER", retain=True)
        self.api_client.publish(f"{API_DEVICE_STATUS_TOPIC}/{serial}", "DISCONNECTED", retain=True)

    def start(self):
        if not self.is_configured:
            logger.error("Cannot start bridge, configuration is invalid.")
            return

        if self.is_started:
            return

        logger.info("Starting Dingtian Bridge clients...")
        try:
            self.api_client.connect("localhost", 1883, 60)
            self.api_client.loop_start()
            self.start_hardware_client()
            self.is_started = True
        except Exception as e:
            logger.error(f"Failed to start MQTT clients: {e}")
            self.is_started = False

    def start_hardware_client(self):
        if not self.is_configured: return
        broker_cfg = self.config['mqtt_broker']
        address = broker_cfg.get('address', 'localhost')
        port = int(broker_cfg.get('port', 1883))
        if broker_cfg.get('username'):
            self.hardware_client.username_pw_set(broker_cfg.get('username'), broker_cfg.get('password'))
            
        logger.info(f"Connecting to Dingtian hardware broker at {address}:{port}")
        self.hardware_client.connect(address, port, 60)
        self.hardware_client.loop_start()

    def on_api_connect(self, client, userdata, flags, rc):
        logger.info("Connected to internal API. Subscribing to topics.")
        client.subscribe(f"{API_RELAY_SET_TOPIC}/#")
        # On connect, we treat all devices in config as "new" compared to an empty set of old devices.
        self.register_devices_with_engine(self.device_configs, {})

    def on_hardware_connect(self, client, userdata, flags, rc):
        logger.info("Connected to Dingtian hardware broker.")
        for cfg in self.device_configs.values():
            topic_base = cfg['topic_base']
            client.subscribe(f"{topic_base}/input/#")
            client.subscribe(f"{topic_base}/relay/+/state")
        for cfg in self.device_configs.values():
            self.api_client.publish(f"{API_DEVICE_STATUS_TOPIC}/{cfg['serial']}", "CONNECTED", retain=True)

    def on_api_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.error("Unexpectedly disconnected from internal API. Reconnecting...")

    def on_hardware_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.error("Unexpectedly disconnected from Dingtian hardware broker. Reconnecting...")
            for cfg in self.device_configs.values():
                self.api_client.publish(f"{API_DEVICE_STATUS_TOPIC}/{cfg['serial']}", "DISCONNECTED", retain=True)

    def on_api_message(self, client, userdata, msg):
        logger.info(f"Received API command: Topic={msg.topic}, Payload={msg.payload.decode()}")
        try:
            parts = msg.topic.split('/')
            if len(parts) == 6 and parts[3] == 'set':
                serial, relay_index, payload = parts[4], int(parts[5]), msg.payload.decode()
                for cfg in self.device_configs.values():
                    if cfg['serial'] == serial:
                        topic_base = cfg['topic_base']
                        hardware_topic = f"{topic_base}/relay/{relay_index-1}/set"
                        result = self.hardware_client.publish(hardware_topic, payload)
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            logger.info(f"Successfully forwarded command to hardware: {hardware_topic} -> {payload}")
                        else:
                            logger.error(f"Failed to forward command. Topic: {hardware_topic}, MQTT Error: {result.rc}")
                        return
                logger.warning(f"Received API command for unknown serial '{serial}'.")
        except Exception as e:
            logger.error(f"Error processing API message: {e}")

    def on_hardware_message(self, client, userdata, msg):
        try:
            parts = msg.topic.split('/')
            topic_base = f"{parts[0]}/{parts[1]}"
            
            serial = next((cfg['serial'] for cfg in self.device_configs.values() if cfg['topic_base'] == topic_base), None)
            if not serial: return

            if len(parts) == 4 and parts[2] == 'input':
                input_index, payload = parts[3], msg.payload.decode()
                api_topic = f"{API_INPUT_STATE_TOPIC}/{serial}/{input_index}"
                self.api_client.publish(api_topic, payload)
        except Exception as e:
            logger.error(f"Error processing hardware message: {e}")

    def stop(self):
        # On shutdown, unregister all currently managed devices.
        logger.info("Stopping bridge. Un-registering all managed devices.")
        for cfg in self.device_configs.values():
            self._unregister_device(cfg['serial'])
        time.sleep(0.5) # Allow time for messages to be sent
        self.api_client.loop_stop()
        self.api_client.disconnect()
        self.hardware_client.loop_stop()
        self.hardware_client.disconnect()
        logger.info("Dingtian Bridge stopped.")

if __name__ == "__main__":
    bridge = DingtianBridge(BRIDGE_CONFIG_FILE)
    
    # Signal handler for graceful shutdown
    def shutdown_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully.")
        bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    bridge.start()

    last_mtime = 0
    try:
        while True:
            if not bridge.is_configured:
                # If not configured, keep trying to reconfigure
                logger.info("Bridge is not configured, attempting to load config...")
                bridge.reconfigure()
                # If configuration is now successful, start the clients
                if bridge.is_configured and not bridge.is_started:
                    bridge.start()
            else:
                # If configured, check for file modifications
                try:
                    if last_mtime == 0: last_mtime = os.path.getmtime(BRIDGE_CONFIG_FILE)
                    current_mtime = os.path.getmtime(BRIDGE_CONFIG_FILE)
                    if current_mtime != last_mtime:
                        logger.info("Dingtian config file changed, reconfiguring...")
                        last_mtime = current_mtime
                        bridge.reconfigure()
                except FileNotFoundError:
                    logger.warning(f"Configuration file '{BRIDGE_CONFIG_FILE}' lost. Will retry.")
                    bridge.is_configured = False # Mark as unconfigured to trigger reload
            
            time.sleep(CONFIG_CHECK_INTERVAL)
            
    except Exception as e:
        logger.error(f"An unexpected error occurred in the main loop: {e}")
    finally:
        # The signal handler will call stop(), so this is a fallback.
        if bridge.is_started:
            bridge.stop()

