pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ComboBox {
    id: root

    property string logoRole: ""
    property var logoModel: []
    implicitHeight: 42
    leftPadding: 12
    rightPadding: 38
    font.pixelSize: Theme.body
    focusPolicy: Qt.TabFocus
    Accessible.name: displayText

    function logoAt(index) {
        if (!logoRole || index < 0 || !logoModel || logoModel[index] === undefined)
            return ""
        const entry = logoModel[index]
        if (typeof entry === "string")
            return entry
        return entry && entry[logoRole] !== undefined ? String(entry[logoRole]) : ""
    }

    contentItem: RowLayout {
        spacing: 8

        PlatformLogo {
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            platform: root.logoAt(root.currentIndex)
            visible: platform.length > 0
        }

        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: root.displayText
            color: root.enabled ? Theme.text : Theme.textDisabled
            font: root.font
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Theme.label
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            elide: Text.ElideNone
        }
    }

    indicator: AppIcon {
        x: root.width - width - 12
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.icon
        height: Theme.icon
        glyph: root.popup.opened ? "\uE70E" : "\uE70D"
        iconColor: root.enabled ? Theme.textMuted : Theme.textDisabled
        iconSize: Theme.iconSmall
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.enabled && root.hovered ? Theme.surfaceMuted : Theme.input
        border.width: root.activeFocus || root.popup.opened ? 2 : 1
        border.color: root.activeFocus || root.popup.opened ? Theme.focus : Theme.outline

        Behavior on color {
            ColorAnimation { duration: Theme.motionFast }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.motionFast }
        }
    }

    popup: Popup {
        id: voicePopup

        y: root.height + 6
        width: root.width
        height: Math.min(292, Math.max(52, voiceList.contentHeight + 12))
        padding: 6
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionFast }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
        }

        contentItem: ListView {
            id: voiceList

            clip: true
            model: root.delegateModel
            currentIndex: root.highlightedIndex
            reuseItems: true
            ScrollIndicator.vertical: ScrollIndicator {}
        }

        background: Rectangle {
            radius: Theme.radius
            color: Theme.surfaceElevated
            border.width: 1
            border.color: Theme.outlineStrong
        }
    }

    delegate: ItemDelegate {
        id: voiceDelegate

        required property int index
        required property var modelData
        readonly property bool optionAvailable: !voiceDelegate.modelData
                                                || voiceDelegate.modelData.available === undefined
                                                || voiceDelegate.modelData.available !== false
        readonly property string optionCategory: voiceDelegate.modelData
            && voiceDelegate.modelData.category !== undefined
            ? String(voiceDelegate.modelData.category) : ""
        readonly property bool showCategory: optionCategory.length > 0
            && (voiceDelegate.index === 0
                || !root.model[voiceDelegate.index - 1]
                || String(root.model[voiceDelegate.index - 1].category || "") !== optionCategory)

        width: root.popup.width - 12
        height: 40 + (showCategory ? 26 : 0)
        enabled: voiceDelegate.optionAvailable
        highlighted: voiceDelegate.enabled && root.highlightedIndex === voiceDelegate.index

        contentItem: ColumnLayout {
            spacing: 0

            Text {
                Layout.fillWidth: true
                Layout.preferredHeight: voiceDelegate.showCategory ? 26 : 0
                visible: voiceDelegate.showCategory
                text: String(voiceDelegate.modelData.categoryLabel || voiceDelegate.optionCategory)
                color: Theme.textSubtle
                font.pixelSize: Theme.caption
                font.weight: Font.DemiBold
                verticalAlignment: Text.AlignBottom
                leftPadding: 8
                textFormat: Text.PlainText
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                PlatformLogo {
                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 22
                    platform: root.logoAt(voiceDelegate.index)
                    visible: platform.length > 0
                }

                Text {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: root.textAt(voiceDelegate.index)
                    color: !voiceDelegate.enabled
                           ? Theme.textDisabled
                           : (voiceDelegate.highlighted ? Theme.interactive : Theme.text)
                    font.pixelSize: Theme.body
                    fontSizeMode: Text.HorizontalFit
                    minimumPixelSize: Theme.label
                    font.weight: voiceDelegate.highlighted ? Font.DemiBold : Font.Normal
                    verticalAlignment: Text.AlignVCenter
                    textFormat: Text.PlainText
                    elide: Text.ElideNone
                }
            }
        }

        background: Rectangle {
            radius: Theme.radiusSmall
            color: voiceDelegate.highlighted ? Theme.interactiveMuted : "transparent"
        }
    }
}
