import QtQuick 1.1
import com.victron.velib 1.0
import "utils.js" as Utils

MbPage {
	id: root

        property string rgpioSettings: "dbus/com.victronenergy.settings/Settings/RemoteGPIO"
        property string serviceSetting: "dbus/com.victronenergy.settings/Settings/Services/RemoteGPIO"

	title: qsTr("RemoteGPIO")


	model: VisualModels {
		VisibleItemModel {
			MbSwitch {
				id: enable
				name: qsTr("Enable")
				bind: serviceSetting
			}

                	MbItemOptions {
                        	id: numberunits
                        	description: qsTr("Number of Units")
				bind: [rgpioSettings, "/NumberUnits"]
				show: enable.checked
                        	possibleValues: [
                        	        MbOption {description: qsTr("1 Unit Installed"); value: 1},
                        	        MbOption {description: qsTr("2 Units Installed"); value: 2}
                        	]
                	}

                        MbItemText {                
                                text: qsTr("Changing the configuration requires to reboot Venus OS")
                                wrapMode: Text.WordWrap                                       
                                show: enable.checked                                          
                        }                                                                     

			MbSubMenu {
				description: qsTr("Unit 1")
				subpage: Component { PageSettingsUnit1 {} }
				show: enable.checked
			}

			MbSubMenu {
				description: qsTr("Unit 2")
				subpage: Component { PageSettingsUnit2 {} }
				show: enable.checked && numberunits.value == 2
			}

                        MbItemOptions {
                                id: protocol
                                description: qsTr("Protocol")
                                bind: [rgpioSettings, "/Protocol"]
                                show: enable.checked
                                possibleValues: [
                                        MbOption {description: qsTr("Modbus via USB"); value: 0},
                                        MbOption {description: qsTr("Modbus via Ethernet"); value: 1}
                                ]
                        }
                                 
                        MbItemOptions {
                                id: latency
                                description: qsTr("Latency")
                                bind: [rgpioSettings, "/Latency"]                            
                                show: enable.checked   
                                possibleValues: [   
                                        MbOption {description: qsTr("Minimum Latency - CPU load will be high"); value: 0},
                                        MbOption {description: qsTr("Medium Latency - CPU load will be arround 4%"); value: 0.1},
                                        MbOption {description: qsTr("High Latency - CPU load will be low"); value: 0.9}
                                ]  
                        }
		}
	}
}
