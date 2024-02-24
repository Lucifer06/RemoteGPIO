// New for GuiMods to show relay info on a separate Overview page

import QtQuick 1.1
import com.victron.velib 1.0
import "utils.js" as Utils
import "tanksensor.js" as TankSensor

OverviewPage
{
	id: root

    property int relayWidth: 0
    property int maxRelays: 6
    property int numberOfRelaysShown: 0
    property int horizontalMargin: 8
    property int tileWidth: (root.width - (horizontalMargin * 2)) / root.maxRelays
    property int listWidth: tileWidth * numberOfRelaysShown
    property int listHeight: root.height - 30

////// GuiMods — DarkMode
	property VBusItem darkModeItem: VBusItem { bind: "com.victronenergy.settings/Settings/GuiMods/DarkMode" }
	property bool darkMode: darkModeItem.valid && darkModeItem.value == 1

    VBusItem
    {
        id: relay12ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/12/Show")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay13ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/13/Show")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay14ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/14/Show")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay15ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/15/Show")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay16ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/16/Show")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay17ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/17/Show")
        onValueChanged: updateRelays ()
    }

    VBusItem
    {
        id: relay12StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/12/State")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay13StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/13/State")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay14StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/14/State")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay15StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/15/State")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay16StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/16/State")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay17StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/17/State")
        onValueChanged: updateRelays ()
    }

    // Synchronise name text scroll start
    Timer
    {
        id: marqueeTimer
        interval: 5000
        repeat: true
        running: root.active
   }

	title: qsTr("Relay overview 13-18")
	clip: true

    Component.onCompleted: updateRelays ()

    // background
    Rectangle
    {
        anchors
        {
            fill: parent
        }
////// GuiMods — DarkMode
		color: !darkMode ? "gray" : "#202020"
    }

    ListModel { id: relaysModel }

    Text
    {
        font.pixelSize: 14
        font.bold: true
        color: "black"
        anchors
        {
            top: parent.top
            topMargin: 7
            horizontalCenter: parent.horizontalCenter
        }
        horizontalAlignment: Text.AlignHCenter
        text: qsTr("Relay overview 13-18")
    }

	ListView
    {
        id: relaysColumn

        anchors.horizontalCenter: root.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 30
        width: listWidth
        height: listHeight
        orientation: ListView.Horizontal
        visible: numberOfRelaysShown > 0
        interactive: false

        model: relaysModel
        delegate: TileRelay
        {
            width: tileWidth
            height: root.height - 38
            Connections
            {
                target: marqueeTimer
                onTriggered: doScroll()
            }
        }
    }

    function updateRelays ()
    {
        var show = false
        numberOfRelaysShown = 0
        relaysModel.clear()
        for (var i = 0; i < maxRelays; i++)
        {
            switch (i)
            {
            case 0:
                show = relay12StateItem.valid && relay12ShowItem.valid && relay12ShowItem.value === 1
                break;;
            case 1:
                show = relay13StateItem.valid && relay13ShowItem.valid && relay13ShowItem.value === 1
                break;;
            case 2:
                show = relay14StateItem.valid && relay14ShowItem.valid && relay14ShowItem.value === 1
                break;;
            case 3:
                show = relay15StateItem.valid && relay15ShowItem.valid && relay15ShowItem.value === 1
                break;;
            case 4:
                show = relay16StateItem.valid && relay16ShowItem.valid && relay16ShowItem.value === 1
                break;;
            case 5:
                show = relay17StateItem.valid && relay17ShowItem.valid && relay17ShowItem.value === 1
                break;;
            default:
                show = false
            }

            if (show)
            {
                numberOfRelaysShown++ // increment before append so ListView centers properly
                relaysModel.append ({relayNumber: i+12})
            }
        }
    }
}
