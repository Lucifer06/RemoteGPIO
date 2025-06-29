import QtQuick 2
import com.victron.velib 1.0
import "utils.js" as Utils

MbPage {
	id: root

	property string adcService: "dbus/com.victronenergy.adc"
	property string settingsService: "dbus/com.victronenergy.settings"

	title: "I/O"

	VeQItemTableModel {
		id: analogModel
		uids: [Utils.path(adcService, "/Devices")]
		flags: VeQItemTableModel.AddChildren |
			   VeQItemTableModel.AddNonLeaves |
			   VeQItemTableModel.DontAddItem
	}

	VeQItemSortTableModel {
		id: digitalModel
		model: VeQItemTableModel {
			uids: [Utils.path(settingsService, "/Settings/DigitalInput")]
			flags: VeQItemTableModel.AddChildren |
				   VeQItemTableModel.AddNonLeaves |
				   VeQItemTableModel.DontAddItem
		}
	}

	property alias numAnalogDevices: analogModel.rowCount
	property alias numDigitalDevices: digitalModel.rowCount
	property bool haveBluetooth: Connman.technologyList.indexOf("bluetooth") !== -1
	property bool haveSubMenus: numAnalogDevices || numDigitalDevices || haveBluetooth

	function disconnectedDeviceToast()
	{
		var text = qsTr("This sensor will remain visible on the devices list, " +
						"Use remove disconnected devices to remove it.")
		toast.createToast(text, 5000)
	}

	model: VisibleItemModel {
		MbSubMenu {
			description: qsTr("Analog inputs")
			show: numAnalogDevices > 0
			subpage: Component {
				MbPage {
					title: qsTr("Analog inputs")
					model: analogModel
					delegate: MbSwitch {
						property VBusItem label: VBusItem {
							bind: [model.uid, "/Label"]
						}
						name: label.value
						bind: [model.uid, "/Function"]
						onCheckedChanged: if (valid && !checked) disconnectedDeviceToast()
					}
				}
			}
		}

		MbSubMenu {
			description: qsTr("Digital inputs")
			show: numDigitalDevices > 0
			subpage: Component {
				MbPage {
					id: digitalInputsPage
					title: qsTr("Digital inputs")
					model: digitalModel
					delegate: MbItemDigitalInput {
						description: qsTr("Digital input") + " " + model.uid.split('/').pop()
						bind: [model.uid, "/Type"]
						onDisabled: disconnectedDeviceToast()
					}
				}
			}
		}

		MbSubMenu {
			description: qsTr("Bluetooth sensors")
			show: haveBluetooth
			subpage: Component { PageSettingsBleSensors {} }
		}
				
		MbSubMenu {
			description: qsTr
			("RemoteGPIO")
			subpage: Component {
			PageSettingsRGPIO {} }
		}
	}
}
