pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property string title: ""
    property int contentMaximumWidth: 920
    readonly property int horizontalInset: UiMetrics.compact ? Theme.space16 : Theme.space24
    default property alias content: contentColumn.data

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 64

            PageHeader {
                anchors {
                    left: parent.left
                    right: parent.right
                    leftMargin: root.horizontalInset
                    rightMargin: root.horizontalInset
                    verticalCenter: parent.verticalCenter
                }
                title: root.title
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        ScrollView {
            id: scrollView

            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                id: contentColumn

                width: Math.min(root.contentMaximumWidth,
                    Math.max(1, scrollView.availableWidth - root.horizontalInset * 2))
                x: Math.max(root.horizontalInset,
                    Math.round((scrollView.availableWidth - width) / 2))
                spacing: 0
            }
        }
    }
}
