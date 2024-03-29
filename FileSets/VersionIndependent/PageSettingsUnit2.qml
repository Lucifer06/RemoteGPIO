import QtQuick 1.1
import com.victron.velib 1.0
import "utils.js" as Utils

MbPage {
	id: root

        property string rgpioSettings: "dbus/com.victronenergy.settings/Settings/RemoteGPIO/Unit2"
        property string serviceSetting: "dbus/com.victronenergy.settings/Settings/Services/RemoteGPIO"

	title: qsTr("Unit 2 Configuration")


	model: VisualModels {
		VisibleItemModel {

	    	MbEditBox {
            	description: qsTr("Unit 2 IP Address")
            	maximumLength: 15
				item.bind: [rgpioSettings, "/IP"]
            	matchString: ".0123456789"
			}

            MbItemOptions {
                id: protocol
                description: qsTr("Protocol")
                bind: [rgpioSettings, "/Protocol"]
                show: enable.checked
                possibleValues: [
                    MbOption {description: qsTr("Modbus via RS485"); value: 0},
                    MbOption {description: qsTr("Modbus via TCP"); value: 1}
                ]
            }

            MbItemOptions {
                id: port
                description: qsTr("USB Port")
                bind: [rgpioSettings, "/USB_Port"]
                show: protocol.value == 0
                possibleValues: [
                    MbOption {description: qsTr("USB0"); value: "/dev/ttyUSB0"},
                    MbOption {description: qsTr("USB1"); value: "/dev/ttyUSB1"}
                ]
            }
                        
        	MbItemText {                                                               
            	text: qsTr("Dingtian IOT Relay device needs to be configured with Addr = 2. This applies for both RS485 and TCP protocols")     
            	wrapMode: Text.WordWrap                                            
        	}    

        	MbSwitch {                                  
            	id: reboot                           
            	name: qsTr("Reboot Unit 2?")                 
				bind: [rgpioSettings, "/Reboot"]
        	}         
		
			MbItemOptions {
            	id: confirm
            	description: qsTr("PLEASE CONFIRM")
				bind: serviceSetting
            	show: reboot.checked
            	possibleValues: [
                	MbOption {description: qsTr("Don't reboot Unit"); value: 1},
                	MbOption {description: qsTr("Yes, Reboot please"); value: 2}
            	]
        	}
		}
	}
}