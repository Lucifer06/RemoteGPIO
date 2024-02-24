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
        id: relay6ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/6/Show")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay7ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/7/Show")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay8ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/8/Show")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay9ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/9/Show")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay10ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/10/Show")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay11ShowItem
        bind: Utils.path("com.victronenergy.settings", "/Settings/Relay/11/Show")
        onValueChanged: updateRelays ()
    }

    VBusItem
    {
        id: relay6StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/6/State")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay7StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/7/State")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay8StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/8/State")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay9StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/9/State")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay10StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/10/State")
        onValueChanged: updateRelays ()
    }
    VBusItem
    {
        id: relay11StateItem
        bind: Utils.path("com.victronenergy.system", "/Relay/11/State")
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

	title: qsTr("Relay overview 7-12")
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
        text: qsTr("Relay overview 7-12")
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
                show = relay6StateItem.valid && relay6ShowItem.valid && relay6ShowItem.value === 1
                break;;
            case 1:
                show = relay7StateItem.valid && relay7ShowItem.valid && relay7ShowItem.value === 1
                break;;
            case 2:
                show = relay8StateItem.valid && relay8ShowItem.valid && relay8ShowItem.value === 1
                break;;
            case 3:
                show = relay9StateItem.valid && relay9ShowItem.valid && relay9ShowItem.value === 1
                break;;
            case 4:
                show = relay10StateItem.valid && relay10ShowItem.valid && relay10ShowItem.value === 1
                break;;
            case 5:
                show = relay11StateItem.valid && relay11ShowItem.valid && relay11ShowItem.value === 1
                break;;
            default:
                show = false
            }

            if (show)
            {
                numberOfRelaysShown++ // increment before append so ListView centers properly
                relaysModel.append ({relayNumber: i+6})
            }
        }
    }
}
