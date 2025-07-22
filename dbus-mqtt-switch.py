#!/usr/bin/env python

# #############################################################################
#
#   dbus-mqtt-switch.py
#
#   A Victron Venus OS driver to integrate a generic MQTT I/O device
#   with 8 relays.
#
#   It uses the mosquitto_pub and mosquitto_sub command-line tools.
#
#   This driver mimics the D-Bus path structure of the official
#   GX IO extender 150 for relays.
#
#   To run from the standard Victron folder, place this file in:
#   /opt/victronenergy/dbus-mqtt-switch/
#
#   And create a service file in:
#   /service/dbus-mqtt-switch
#
# #############################################################################

from gi.repository import GLib
import logging
import sys
import os
import subprocess
import threading

# Make sure the path includes Victron libraries
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from vedbus import VeDbusService

# ####################################################################
# ## General & MQTT Configuration
# ####################################################################

# Number of relays to create
NUM_RELAYS = 8

# MQTT Broker Configuration
MQTT_BROKER_ADDRESS = "localhost"  # Use "localhost" if the broker is on the same device
MQTT_PORT = 1883
MQTT_USERNAME = None  # Set a username if required
MQTT_PASSWORD = None  # Set a password if required

# MQTT Device Serial Number
# Mettez ici le numéro de série de votre appareil MQTT
MQTT_DEVICE_SERIAL = "MQTT-IO-001" 

# MQTT Topic Structure Configuration
# The driver will subscribe to: <MQTT_TOPIC_BASE>/relay/+/state
# It will publish commands to: <MQTT_TOPIC_BASE>/relay/<index>/set
MQTT_TOPIC_BASE = "dingtian" # Example: "dingtian/relay/0/state"

# The exact payloads your module sends/expects for 'ON' and 'OFF'
MQTT_PAYLOAD_ON = "ON"
MQTT_PAYLOAD_OFF = "OFF"
# ####################################################################


class DbusMqttIoService:
    def __init__(self, servicename='com.victronenergy.switch.mqtt_io', deviceinstance=50): # Using instance 50 from reference
        self._dbusservice = VeDbusService(servicename)
        self._deviceinstance = deviceinstance
        self._is_connected = False
        self._listener_thread = None

        logging.info("Starting MQTT I/O Driver")

        # Create the management D-Bus entries
        self._dbusservice.add_path('/Management/ProcessName', __file__)
        self._dbusservice.add_path('/Management/ProcessVersion', '1.6')
        self._dbusservice.add_path('/Management/Connection', f'MQTT: {MQTT_BROKER_ADDRESS}')

        # Create device-level D-Bus entries based on GX IO extender 150
        self._dbusservice.add_path('/DeviceInstance', deviceinstance)
        self._dbusservice.add_path('/ProductId', 19191)
        self._dbusservice.add_path('/ProductName', 'MQTT IO extender')
        self._dbusservice.add_path('/FirmwareVersion', '1.6 (dbus-mqtt-switch)')
        self._dbusservice.add_path('/HardwareVersion', 'N/A')
        self._dbusservice.add_path('/Connected', 0) # Start as disconnected
        self._dbusservice.add_path('/CustomName', 'MQTT I/O Module', writeable=True)
        self._dbusservice.add_path('/Serial', MQTT_DEVICE_SERIAL)
        
        # Add a single /State path to reflect connection status.
        # 0 = Disconnected, 254 = Connected.
        self._dbusservice.add_path('/State', 0) # Start as disconnected

        # Create D-Bus paths for Relays (SwitchableOutput) following GX IO extender convention
        logging.info(f"Creating {NUM_RELAYS} relays...")
        for i in range(NUM_RELAYS):
            relay_id = i + 1
            base_path = f'/SwitchableOutput/relay_{relay_id}'
            
            # The main state path that is controllable
            self._dbusservice.add_path(f'{base_path}/State', 0, writeable=True,
                                       onchangecallback=lambda path, value, index=i: self._handle_relay_change(index, path, value))
            
            # Add other paths to match the GX IO extender structure
            self._dbusservice.add_path(f'{base_path}/Name', f'MQTT Relay {relay_id}')
            self._dbusservice.add_path(f'{base_path}/Status', 0) # Status can be updated if needed
            self._dbusservice.add_path(f'{base_path}/Settings/CustomName', '', writeable=True)
            self._dbusservice.add_path(f'{base_path}/Settings/Function', 2)
            self._dbusservice.add_path(f'{base_path}/Settings/Group', '', writeable=True)
            self._dbusservice.add_path(f'{base_path}/Settings/ShowUIControl', 1)
            self._dbusservice.add_path(f'{base_path}/Settings/Type', 1)
            self._dbusservice.add_path(f'{base_path}/Settings/ValidFunctions', 4)
            self._dbusservice.add_path(f'{base_path}/Settings/ValidTypes', 3)

        # Start listening for MQTT messages in a background thread
        self.start_mqtt_listener()

    def _set_connection_state(self, connected):
        """ Met à jour l'état de connexion sur D-Bus. """
        if connected and not self._is_connected:
            logging.info("Connection to MQTT device established.")
            self._dbusservice['/State'] = 254
            self._dbusservice['/Connected'] = 1
            self._is_connected = True
        elif not connected and self._is_connected:
            logging.warning("Connection to MQTT device lost.")
            self._dbusservice['/State'] = 0
            self._dbusservice['/Connected'] = 0
            self._is_connected = False
            # Tentative de reconnexion
            logging.info("Attempting to restart listener in 10 seconds...")
            GLib.timeout_add_seconds(10, self._restart_listener)
        return False

    def _restart_listener(self):
        """ Redémarre le listener si la connexion est perdue. """
        if not self._is_connected:
            self.start_mqtt_listener()
        return False # Empêche GLib.timeout_add de se répéter

    def start_mqtt_listener(self):
        """ Spawns the mosquitto_sub process to listen for all I/O state changes. """
        if self._listener_thread and self._listener_thread.is_alive():
            logging.info("Mosquitto listener thread is already running.")
            return

        logging.info("Starting Mosquitto listener thread...")
        
        # Subscribe only to relay state topics
        topic_to_subscribe = f"{MQTT_TOPIC_BASE}/relay/+/state"
        
        cmd = [
            'mosquitto_sub',
            '-h', MQTT_BROKER_ADDRESS,
            '-p', str(MQTT_PORT),
            '-t', topic_to_subscribe,
            '-F', '%t %p',
            '-i', f'dbus-mqtt-switch-sub-{self._deviceinstance}',
        ]
        if MQTT_USERNAME:
            cmd.extend(['-u', MQTT_USERNAME])
        if MQTT_PASSWORD:
            cmd.extend(['-P', MQTT_PASSWORD])

        self._listener_thread = threading.Thread(target=self._run_listener, args=(cmd,), daemon=True)
        self._listener_thread.start()

    def _run_listener(self, cmd):
        """ Function executed in the thread to read mosquitto_sub's output. """
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            for line in iter(process.stdout.readline, ''):
                # Le premier message reçu confirme la connexion
                if not self._is_connected:
                    GLib.idle_add(self._set_connection_state, True)

                try:
                    topic, payload = line.strip().split(' ', 1)
                    parts = topic.split('/')
                    # Expects <base>/relay/<index>/state
                    if len(parts) == 4 and parts[1] == 'relay':
                        index = int(parts[2]) # 0, 1, 2...
                        GLib.idle_add(self._update_state_from_mqtt, index, payload)

                except (ValueError, IndexError) as e:
                    logging.warning(f"Could not parse MQTT message: '{line.strip()}' - Error: {e}")

        except FileNotFoundError:
            logging.error("Command 'mosquitto_sub' not found. Please ensure it is installed and in the system's PATH.")
        except Exception as e:
            logging.error(f"Error in Mosquitto listener thread: {e}")
        finally:
            # Si la boucle se termine, le processus mosquitto_sub s'est arrêté, donc nous sommes déconnectés.
            if self._is_connected:
                GLib.idle_add(self._set_connection_state, False)

    def _update_state_from_mqtt(self, index, payload):
        """ Updates the D-Bus state from the received MQTT message. """
        logging.info(f"MQTT message received for relay {index}: {payload}")
        
        new_state = 1 if payload == MQTT_PAYLOAD_ON else 0
        
        if 0 <= index < NUM_RELAYS:
            relay_id = index + 1
            dbus_path = f'/SwitchableOutput/relay_{relay_id}/State'
            if self._dbusservice.get_value(dbus_path) != new_state:
                self._dbusservice.set_value(dbus_path, new_state)
                logging.info(f"D-Bus path {dbus_path} updated to {new_state}.")
            
        return False

    def _handle_relay_change(self, index, path, value):
        """ Handles change requests for a relay from D-Bus (e.g., from the GUI). """
        if not self._is_connected:
            logging.warning(f"Cannot change relay {index}: MQTT device is disconnected.")
            return False

        logging.info(f"Relay {index} state change requested via D-Bus to {value}")
        
        payload_to_send = MQTT_PAYLOAD_ON if value == 1 else MQTT_PAYLOAD_OFF
        command_topic = f"{MQTT_TOPIC_BASE}/relay/{index}/set"

        cmd = [
            'mosquitto_pub',
            '-h', MQTT_BROKER_ADDRESS,
            '-p', str(MQTT_PORT),
            '-t', command_topic,
            '-m', payload_to_send,
            '-i', f'dbus-mqtt-switch-pub-{self._deviceinstance}'
        ]
        if MQTT_USERNAME:
            cmd.extend(['-u', MQTT_USERNAME])
        if MQTT_PASSWORD:
            cmd.extend(['-P', MQTT_PASSWORD])

        try:
            logging.info(f"Sending Mosquitto command: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            logging.error("Command 'mosquitto_pub' not found.")
            return False
        except subprocess.CalledProcessError as e:
            logging.error(f"Error sending Mosquitto command for relay {index}: {e.stderr}")
            return False
        
        return True

def main():
    logging.basicConfig(level=logging.INFO)
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    
    # Create and run the service, keeping a reference to it
    service = DbusMqttIoService()
    
    logging.info("D-Bus service (MQTT I/O) started and running.")
    mainloop = GLib.MainLoop()
    mainloop.run()

if __name__ == "__main__":
    main()
