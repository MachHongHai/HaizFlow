pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppSurface {
    id: root

    property var model: null
    readonly property ActivityLogDialog technicalLogDialog: technicalLogLoader.item as ActivityLogDialog

    padding: Theme.space8
    spacing: Theme.space4

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            text: qsTr("Hoạt động")
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }

        StudioButton {
            text: qsTr("Log kỹ thuật")
            variant: "ghost"
            onClicked: {
                if (technicalLogLoader.status === Loader.Ready && root.technicalLogDialog)
                    root.technicalLogDialog.open()
                else
                    technicalLogLoader.active = true
            }
        }
    }

    ListView {
        id: feedList
        Layout.fillWidth: true
        Layout.fillHeight: true
        model: root.model
        clip: true
        reuseItems: true
        boundsBehavior: Flickable.StopAtBounds

        delegate: ActivityRow {
            width: feedList.width
        }

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        onCountChanged: if (count > 0) positionViewAtEnd()
    }

    Text {
        Layout.fillWidth: true
        Layout.fillHeight: true
        visible: feedList.count === 0
        text: qsTr("Hoạt động xử lý sẽ hiện ở đây.")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
    }

    Loader {
        id: technicalLogLoader
        active: false
        asynchronous: false
        onLoaded: if (status === Loader.Ready && root.technicalLogDialog) root.technicalLogDialog.open()
        sourceComponent: Component {
            ActivityLogDialog {
                logText: AppController.logs
                detailText: qsTr("Log kỹ thuật")
                onClosed: technicalLogLoader.active = false
            }
        }
    }
}
