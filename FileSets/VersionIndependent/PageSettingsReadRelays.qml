import QtQuick 1.1
import com.victron.velib 1.0
import "utils.js" as Utils

MbPage {
	id: root

        property string rgpioSettings: "dbus/com.victronenergy.settings/Settings/RemoteGPIO/ReadRelays"
        property string serviceSetting: "dbus/com.victronenergy.settings/Settings/Services/RemoteGPIO"

	title: qsTr("Read Remote Relay Status")


	model: VisualModels {
		VisibleItemModel {


        	MbItemText {                                                               
            	text: qsTr("Users that have relay modules that are able to be controlled outside of the venus device (ie. relays that can be switched from devices/switches that are connected directly to the relay module) may find this feature useful. Enabling this feature will cause RemoteGPIO to poll the relay modules for current state and dynamically update the GUI")     
            	wrapMode: Text.WordWrap                                            
        	}
			MbItemText {                                                               
            	text: qsTr("REQUIRES SYSTEM REBOOT")     
            	wrapMode: Text.WordWrap                                            
        	} 

        	MbSwitch {                                  
            	id: readrelay                           
            	name: qsTr("Enable")                 
				bind: rgpioSettings
        	}         
		}
	}
}
