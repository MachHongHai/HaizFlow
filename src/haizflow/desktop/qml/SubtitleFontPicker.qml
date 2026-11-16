pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Control {
    id: root
    property string family: "Bangers"
    property string language: "vi"
    property var catalog: []
    property var choices: []
    signal fontSelected(string value)
    implicitWidth: fields.implicitWidth
    implicitHeight: fields.implicitHeight

    function filterFonts() {
        const query = search.text.trim().toLowerCase();
        const category = ["", "sans", "serif", "display"][categoryPicker.currentIndex];
        choices = catalog.filter(function(row) {
            return (!query || row.family.toLowerCase().indexOf(query) >= 0)
                && (!category || row.category === category);
        });
        fontList.currentIndex = choices.findIndex(function(row) { return row.family === root.family; });
        fontList.positionViewAtBeginning();
        if (fontList.currentIndex >= 0)
            fontList.positionViewAtIndex(fontList.currentIndex, ListView.Contain);
    }

    function selectCurrentFont() {
        if (fontList.currentIndex >= 0) {
            root.fontSelected(root.choices[fontList.currentIndex].family);
            picker.close();
        }
    }

    contentItem: ColumnLayout {
        id: fields
        spacing: Theme.space8
        SettingLabel { text: qsTr("Phông chữ") }
        StudioButton {
            id: trigger
            objectName: "subtitleFontButton"
            Layout.fillWidth: true
            text: root.family
            Accessible.name: qsTr("Chọn phông chữ: %1").arg(root.family)
            onClicked: picker.open()
            contentItem: RowLayout {
                Text {
                    Layout.fillWidth: true
                    text: root.family
                    color: root.enabled ? Theme.text : Theme.textDisabled
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.control
                    elide: Text.ElideRight
                }
                AppIcon {
                    Layout.preferredWidth: Theme.icon
                    Layout.preferredHeight: Theme.icon
                    glyph: picker.opened ? "\uE70E" : "\uE70D"
                    iconColor: Theme.textMuted
                    iconSize: Theme.iconSmall
                }
            }
        }
    }

    Popup {
        id: picker
        objectName: "subtitleFontPopup"
        parent: Overlay.overlay
        implicitWidth: Math.min(410, parent ? parent.width - 24 : 410)
        implicitHeight: Math.min(490, parent ? parent.height - 24 : 490)
        property point anchorPoint: Qt.point(0, 0)
        x: Math.max(12, Math.min(anchorPoint.x, parent ? parent.width - width - 12 : 12))
        y: parent && anchorPoint.y + height <= parent.height - 12 ? anchorPoint.y
            : Math.max(12, anchorPoint.y - trigger.height - height - 12)
        padding: Theme.space12
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onAboutToShow: {
            anchorPoint = trigger.mapToItem(parent, 0, trigger.height + 6);
            root.catalog = AppController.subtitleFontChoices(root.language, "");
            search.clear();
            categoryPicker.currentIndex = 0;
            root.filterFonts();
        }
        onOpened: search.forceActiveFocus()
        onClosed: {
            root.catalog = [];
            root.choices = [];
            trigger.forceActiveFocus();
        }
        background: Rectangle {
            color: Theme.surfaceElevated
            radius: Theme.radius
            border.color: Theme.outlineStrong
        }
        contentItem: ColumnLayout {
            spacing: Theme.space12
            RowLayout {
                Layout.fillWidth: true
                SearchField {
                    id: search
                    objectName: "subtitleFontSearch"
                    Layout.fillWidth: true
                    placeholderText: qsTr("Tìm phông chữ")
                    onTextChanged: root.filterFonts()
                    Keys.onDownPressed: { fontList.forceActiveFocus(); fontList.currentIndex = 0; }
                }
                StudioComboBox {
                    id: categoryPicker
                    objectName: "subtitleFontCategory"
                    Layout.preferredWidth: 125
                    model: [qsTr("Tất cả"), qsTr("Không chân"), qsTr("Có chân"), qsTr("Trang trí")]
                    Accessible.name: qsTr("Kiểu phông chữ")
                    onActivated: root.filterFonts()
                }
            }
            ListView {
                id: fontList
                objectName: "subtitleFontList"
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: root.choices
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                keyNavigationEnabled: true
                highlightMoveDuration: 0
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                Keys.onReturnPressed: root.selectCurrentFont()
                Keys.onEnterPressed: root.selectCurrentFont()
                delegate: ItemDelegate {
                    id: row
                    required property var modelData
                    required property int index
                    width: fontList.width
                    height: 78
                    leftPadding: Theme.space12
                    rightPadding: Theme.space12
                    Accessible.name: modelData.family
                    onClicked: { root.fontSelected(modelData.family); picker.close(); }
                    background: Rectangle {
                        radius: Theme.radiusSmall
                        color: row.modelData.family === root.family ? Theme.interactiveMuted
                            : row.hovered || row.activeFocus || (fontList.activeFocus && fontList.currentIndex === row.index)
                              ? Theme.surfaceStrong : "transparent"
                    }
                    contentItem: ColumnLayout {
                        spacing: Theme.space4
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                Layout.fillWidth: true
                                text: row.modelData.family === "Bangers" ? qsTr("Bangers · Mặc định") : row.modelData.family
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.label
                                color: Theme.textMuted
                                elide: Text.ElideRight
                            }
                            Text {
                                text: row.modelData.family === root.family ? "✓" : ""
                                color: Theme.interactive
                                font.pixelSize: TypeScale.section
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.sample
                            font.family: row.modelData.qtFamily
                            font.weight: row.modelData.weight
                            font.pixelSize: TypeScale.title
                            color: Theme.text
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }
                    }
                }
                Text {
                    anchors.centerIn: parent
                    visible: root.choices.length === 0
                    text: qsTr("Không tìm thấy phông chữ")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.body
                }
            }
        }
    }
}
