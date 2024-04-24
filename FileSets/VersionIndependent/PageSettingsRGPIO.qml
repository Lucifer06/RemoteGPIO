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
					MbOption {description: qsTr("2 Units Installed"); value: 2},
                	MbOption {description: qsTr("3 Units Installed"); value: 3}
            	]
            }

            MbItemText {                
                text: qsTr("Changing the configuration requires to restart service")
                wrapMode: Text.WordWrap                                       
                show: enable.checked                                          
            }                                                                     

			MbSubMenu {
				description: qsTr("Unit 1")
				subpage: Component { PageSettingsUnit1 {} }
				show: enable.checked && (numberunits.value == 1 || numberunits.value == 2 || numberunits.value == 3)
			}

			MbSubMenu {
				description: qsTr("Unit 2")
				subpage: Component { PageSettingsUnit2 {} }
				show: enable.checked && (numberunits.value == 2 || numberunits.value == 3)
			}

			MbSubMenu {
				description: qsTr("Unit 3")
				subpage: Component { PageSettingsUnit3 {} }
				show: enable.checked && numberunits.value == 3
			}

			MbSwitch {                                  
            	id: restart                           
            	name: qsTr("Restart RemoteGPIO Service")
				bind: [rgpioSettings, "/Restart"]
				show: enable.checked                 
        	}         
		
			MbItemOptions {
            	id: confirm
            	description: qsTr("PLEASE CONFIRM")
				bind: serviceSetting
            	show: restart.checked
            	possibleValues: [
                	MbOption {description: qsTr("Restart Service"); value: 3},
                	MbOption {description: qsTr("Do Not Restart Service"); value: 1}
            	]
        	}
		}
	}
}
