#!/bin/bash

# ===================================================================
# Script de nettoyage AGRESSIF pour les paramètres DBus.
# ATTENTION: Ce script arrête des services critiques. Un redémarrage
# est OBLIGATOIRE après son exécution.
# Utilisation : ./cleanup_inputs.sh /chemin/vers/votre/fichier_de_parametres.txt
# ===================================================================

# Vérifier si un fichier est passé en paramètre
if [ -z "$1" ]; then
    echo "Erreur : Vous devez fournir un fichier contenant les chemins des paramètres à supprimer."
    echo "Utilisation : $0 /chemin/vers/fichier.txt"
    exit 1
fi

if [ ! -f "$1" ]; then
    echo "Erreur : Le fichier '$1' est introuvable."
    exit 1
fi

# Liste des services à arrêter. Ajoutez-en d'autres si nécessaire.
SERVICES_TO_STOP=(
    "/service/dbus-digitalinputs"
    "/service/gui-v1"
    "/service/dbus-systemcalc-py"
)

echo "--- Démarrage du nettoyage AGRESSIF des paramètres DBus ---"
echo "ATTENTION: Des services critiques vont être arrêtés."

# Étape 1: Arrêter les services dépendants
for service in "${SERVICES_TO_STOP[@]}"; do
    if [ -d "$service" ]; then
        echo "Arrêt du service : $service"
        svc -d "$service"
    fi
done
echo "Attente de 3 secondes pour que les services s'arrêtent..."
sleep 3

# Lire les lignes depuis le fichier passé en paramètre
mapfile -t LINES_FROM_FILE < "$1"

echo "--- Tentative de suppression des paramètres ---"
echo "Lecture des paramètres à supprimer depuis : $1"
echo "--------------------------------------------------------"

# Boucler sur chaque ligne lue du fichier
for line in "${LINES_FROM_FILE[@]}"; do
    # Ne rien faire si la ligne est vide ou un commentaire
    [[ -z "$line" || "$line" == \#* ]] && continue

    # Extraire uniquement le premier champ de la ligne comme chemin du paramètre
    SETTING_PATH_FROM_FILE=$(echo "$line" | awk '{print $1}')

    # Si après l'extraction le chemin est vide, on passe à la ligne suivante
    if [ -z "$SETTING_PATH_FROM_FILE" ]; then
        continue
    fi

    # Normaliser le chemin pour qu'il commence toujours par une seule barre oblique '/'
    DBUS_PATH_ARG="/$(echo "$SETTING_PATH_FROM_FILE" | sed 's:^/*::')"

    echo "  - Tentative de suppression de ${DBUS_PATH_ARG}"
    
    # Construction de la commande dans une variable pour l'afficher
    COMMAND_TO_RUN="dbus-send --system --type=method_call --dest=com.victronenergy.settings / com.victronenergy.settings.RemoveSetting string:\"$DBUS_PATH_ARG\""
    echo "    [DEBUG] Commande exécutée : $COMMAND_TO_RUN"
    
    # Exécuter la commande et capturer la sortie et les erreurs
    OUTPUT=$(dbus-send --system --type=method_call --dest=com.victronenergy.settings \
        / com.victronenergy.settings.RemoveSetting "string:$DBUS_PATH_ARG" 2>&1)
    
    # Vérifier si la commande a réussi
    if [ $? -ne 0 ]; then
        echo "    ERREUR: La commande dbus-send a échoué. Sortie :"
        echo "    $OUTPUT"
    else
        echo "    Commande exécutée avec succès."
    fi
    
    # Petite pause pour ne pas surcharger dbus
    sleep 0.1
done

echo "--- Nettoyage terminé ---"
echo ""
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
echo "IMPORTANT: Les services ont été arrêtés et ne seront PAS"
echo "redémarrés. Vous DEVEZ redémarrer l'appareil maintenant."
echo "Exécutez la commande : reboot"
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"


