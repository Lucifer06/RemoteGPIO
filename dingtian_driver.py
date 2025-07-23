#!/usr/bin/env python3

import configparser
import paho.mqtt.client as mqtt
import os
import sys
import logging
from gi.repository import GObject
import dbus
import dbus.mainloop.glib

# Importe la librairie Victron pour DBus
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-digitalinputs/ext/velib_python'))
from vedbus import VeDbusService

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DingtianDriver")

class DingtianMqttDriver:
    def __init__(self, config_path):
        self.config = configparser.ConfigParser()
        if not os.path.exists(config_path):
            logger.error(f"Fichier de configuration introuvable : {config_path}")
            sys.exit(1)
        self.config.read(config_path)
        
        self.devices = []
        self._dbus_services = {}

        # Initialisation du client MQTT
        broker_config = self.config['mqtt_broker']
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        if broker_config.get('username'):
            self.mqtt_client.username_pw_set(broker_config['username'], broker_config.get('password'))
        
        logger.info(f"Connexion au broker MQTT à {broker_config['address']}:{broker_config['port']}")
        self.mqtt_client.connect(broker_config['address'], int(broker_config['port']), 60)
        self.mqtt_client.loop_start()

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connecté au broker MQTT avec succès")
            # Souscrire aux topics de tous les appareils configurés
            for section_name in self.config.sections():
                if section_name.startswith('device_'):
                    topic_base = self.config[section_name]['topic_base']
                    # IMPORTANT : Adaptez ce topic au format exact du SDK Dingtian
                    # Exemple : dingtian/+/input/# ou dingtian/+/state
                    subscription_topic = f"{topic_base}/input/#" 
                    logger.info(f"Souscription au topic : {subscription_topic}")
                    self.mqtt_client.subscribe(subscription_topic)
        else:
            logger.error(f"Échec de la connexion MQTT, code de retour : {rc}")

    def on_mqtt_message(self, client, userdata, msg):
        logger.info(f"Message reçu - Topic: {msg.topic}, Payload: {msg.payload.decode()}")
        
        # --- LOGIQUE À ADAPTER À VOTRE SDK DINGTIAN ---
        # Cette partie doit être modifiée pour correspondre exactement aux topics
        # et aux formats de message de votre appareil.
        # Hypothèse : le topic est de la forme "dingtian/<id>/input/<input_num>"
        # et le payload est "0" ou "1".

        try:
            parts = msg.topic.split('/')
            topic_base = f"{parts[0]}/{parts[1]}"
            input_index = int(parts[3]) - 1 # Les entrées sont souvent 1-based
            new_state = int(msg.payload.decode())

            # Trouver le service DBus correspondant
            service_key = f"{topic_base}_{input_index}"
            if service_key in self._dbus_services:
                service = self._dbus_services[service_key]
                # Mettre à jour la valeur sur DBus si elle a changé
                if service['/State'] != new_state:
                    logger.info(f"Mise à jour DBus pour {service.serviceName}: /State -> {new_state}")
                    service['/State'] = new_state
            else:
                logger.warning(f"Aucun service DBus trouvé pour la clé {service_key}")

        except (IndexError, ValueError) as e:
            logger.error(f"Impossible de parser le message MQTT : {msg.topic} - {e}")
        # --- FIN DE LA LOGIQUE À ADAPTER ---

    def setup_devices(self):
        for section_name in self.config.sections():
            if section_name.startswith('device_'):
                device_info = self.config[section_name]
                serial = device_info['serial']
                topic_base = device_info['topic_base']
                num_inputs = int(device_info.get('num_relays', 8)) # Utilise num_relays comme num_inputs
                device_instance = int(device_info['device_instance'])

                logger.info(f"Configuration de l'appareil {serial} avec {num_inputs} entrées.")

                for i in range(num_inputs):
                    # Chaque entrée numérique est un service DBus distinct
                    service_name = f"com.victronenergy.digitalinput.{serial.replace('-', '_')}_input{i+1}"
                    
                    service = VeDbusService(service_name)
                    
                    # --- Création des objets DBus ---
                    service.add_path('/Mgmt/ProcessName', __file__)
                    service.add_path('/Mgmt/ProcessVersion', '1.0')
                    service.add_path('/Mgmt/Connection', f"MQTT: {topic_base}")
                    service.add_path('/DeviceInstance', device_instance + i) # Instance unique par entrée
                    service.add_path('/ProductId', 0) # 0 pour les produits génériques
                    service.add_path('/ProductName', f"Dingtian {serial} - Input {i+1}")
                    service.add_path('/State', 0, writeable=True) # 0=Off, 1=On. L'état initial
                    
                    # Stocker une référence au service
                    service_key = f"{topic_base}_{i}"
                    self._dbus_services[service_key] = service

def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    
    # Le chemin vers votre fichier de configuration
    config_file_path = '/data/RemoteGPIO/conf/config.ini'
    
    driver = DingtianMqttDriver(config_file_path)
    driver.setup_devices()
    
    logger.info("Driver démarré. En attente des messages MQTT...")
    mainloop = GObject.MainLoop()
    mainloop.run()

if __name__ == "__main__":
    main()
