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
                id: numrelays
                description: qsTr("Number of Relays")
                bind: [rgpioSettings, "/NumRelays"]
                show: enable.checked
                possibleValues: [
                    MbOption {description: qsTr("2 Relays"); value: 2},
                    MbOption {description: qsTr("4 Relays"); value: 4},
                    MbOption {description: qsTr("8 Relays"); value: 8}
                ]
            }

            MbItemOptions {
                id: port
                description: qsTr("USB Port")
                bind: [rgpioSettings, "/USB_Port"]
                show: protocol.value == 0
                possibleValues: [
                    MbOption {description: qsTr("USB0"); value: "/dev/ttyUSB0"},
					MbOption {description: qsTr("USB1"); value: "/dev/ttyUSB1"},
                    MbOption {description: qsTr("USB2"); value: "/dev/ttyUSB2"}
                ]
            }

			MbSubMenu {
				description: qsTr("Additional Options")
				subpage: Component { PageSettingsUnit2Options {} }
			}
                        
        	MbItemText {                                                               
            	text: qsTr("Relay module needs to be configured with Addr = 2. This applies for both RS485 and TCP protocols. When using TCP both TCP server and TCP client protocols must select RTU over TCP. Total number of relays for ALL connected modules MUST NOT exceed 16!")     
            	wrapMode: Text.WordWrap                                            
        	}    
		}
	}
}