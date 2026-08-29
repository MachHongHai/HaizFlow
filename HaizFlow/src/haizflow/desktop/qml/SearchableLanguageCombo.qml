pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root
    objectName: "targetLanguagePicker"

    property var options: []
    property var filteredModel: []
    property string selectedCode: ""
    property string placeholderText: qsTr("Tìm ngôn ngữ")
    signal selected(string code)

    implicitHeight: 42

    function labelFor(code) {
        for (let i = 0; i < options.length; i++) {
            if (options[i].code === code)
                return options[i].label;
        }
        return code;
    }

    function indexFor(code, source) {
        const model = source || options;
        for (let i = 0; i < model.length; i++) {
            if (model[i].code === code)
                return i;
        }
        return model.length > 0 ? 0 : -1;
    }

    function filterOptions(queryText) {
        const query = queryText.toLowerCase().trim();
        if (query.length === 0)
            return options;

        const result = [];
        for (let i = 0; i < options.length; i++) {
            if (options[i].search.indexOf(query) !== -1)
                result.push(options[i]);
        }
        return result;
    }

    function openPicker(focusSearch) {
        if (!root.enabled)
            return;
        root.filteredModel = root.filterOptions(searchField.text);
        if (!languagePopup.opened)
            languagePopup.open();
        if (focusSearch) {
            Qt.callLater(function () {
                if (languagePopup.opened)
                    searchField.forceActiveFocus();
            });
        }
    }

    Component.onCompleted: filteredModel = options
    onOptionsChanged: filteredModel = root.filterOptions(searchField.text)
    onVisibleChanged: {
        if (!visible)
            languagePopup.close();
    }

    Button {
        id: displayButton
        objectName: "languageDisplayButton"

        anchors.fill: parent
        enabled: root.enabled
        focusPolicy: Qt.TabFocus
        leftPadding: 12
        rightPadding: 40
        Accessible.name: qsTr("Dịch sang") + ": " + root.labelFor(root.selectedCode)

        contentItem: Text {
            text: root.labelFor(root.selectedCode)
            color: displayButton.enabled ? Theme.text : Theme.textDisabled
            font.pixelSize: Theme.body
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

        background: Rectangle {
            color: displayButton.hovered ? Theme.surfaceMuted : Theme.input
            radius: Theme.radiusSmall
            border.width: displayButton.activeFocus || languagePopup.opened ? 2 : 1
            border.color: displayButton.activeFocus || languagePopup.opened ? Theme.focus : Theme.outline
        }

        AppIcon {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            width: Theme.icon
            height: Theme.icon
            glyph: languagePopup.opened ? "\uE70E" : "\uE70D"
            iconColor: displayButton.enabled ? Theme.textMuted : Theme.textDisabled
            iconSize: Theme.iconSmall
        }

        Keys.onDownPressed: function (event) {
            root.openPicker(false);
            languageList.forceActiveFocus();
            event.accepted = true;
        }
        onClicked: root.openPicker(true)
    }

    Popup {
        id: languagePopup
        objectName: "languageSearchPopup"

        y: root.height + 6
        width: root.width
        height: Math.min(340, Math.max(104, languageList.contentHeight + searchField.implicitHeight + 24))
        padding: 6
        modal: false
        focus: true
        z: 100
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        onOpened: {
            languageList.currentIndex = root.indexFor(root.selectedCode, root.filteredModel);
            searchField.forceActiveFocus();
        }
        onClosed: {
            searchField.text = "";
            root.filteredModel = root.options;
        }

        enter: Transition {
            NumberAnimation {
                property: "opacity"
                from: 0
                to: 1
                duration: Theme.motionFast
            }
        }
        exit: Transition {
            NumberAnimation {
                property: "opacity"
                from: 1
                to: 0
                duration: Theme.motionFast
            }
        }

        background: Rectangle {
            color: Theme.surfaceElevated
            radius: Theme.radius
            border.color: Theme.outlineStrong
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 6

            TextField {
                id: searchField
                objectName: "languageSearchInput"

                Layout.fillWidth: true
                implicitHeight: 40
                placeholderText: root.placeholderText
                selectByMouse: true
                color: root.enabled ? Theme.text : Theme.textDisabled
                placeholderTextColor: Theme.textSubtle
                font.pixelSize: Theme.body
                leftPadding: 12
                rightPadding: 38
                verticalAlignment: TextInput.AlignVCenter
                Accessible.name: qsTr("Tìm ngôn ngữ")

                background: Rectangle {
                    color: searchField.hovered ? Theme.surfaceMuted : Theme.input
                    radius: Theme.radiusSmall
                    border.width: searchField.activeFocus ? 2 : 1
                    border.color: searchField.activeFocus ? Theme.focus : Theme.outline
                }

                AppIcon {
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    width: Theme.icon
                    height: Theme.icon
                    glyph: "\uE721"
                    iconColor: root.enabled ? Theme.textMuted : Theme.textDisabled
                    iconSize: Theme.iconSmall
                }

                onTextEdited: {
                    root.filteredModel = root.filterOptions(text + (inputMethodComposing ? preeditText : ""));
                    languageList.currentIndex = root.indexFor(root.selectedCode, root.filteredModel);
                }
                onPreeditTextChanged: root.filteredModel = root.filterOptions(text + preeditText)

                Keys.onDownPressed: function (event) {
                    languageList.forceActiveFocus();
                    event.accepted = true;
                }
                Keys.onReturnPressed: function (event) {
                    if (root.filteredModel.length === 1)
                        root.selected(root.filteredModel[0].code);
                    languagePopup.close();
                    event.accepted = true;
                }
                Keys.onEscapePressed: function (event) {
                    languagePopup.close();
                    event.accepted = true;
                }
            }

            ListView {
                id: languageList

                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: root.filteredModel
                reuseItems: true
                keyNavigationEnabled: true

                delegate: Item {
                    id: row

                    required property int index
                    required property var modelData

                    readonly property bool selectedOption: modelData && modelData.code === root.selectedCode

                    width: ListView.view.width
                    height: 40
                    activeFocusOnTab: false

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.radiusSmall
                        color: row.selectedOption || rowHover.hovered || languageList.currentIndex === row.index ? Theme.interactiveMuted : "transparent"
                    }

                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        text: row.modelData ? row.modelData.label : ""
                        color: row.selectedOption ? Theme.interactive : Theme.text
                        font.pixelSize: Theme.body
                        font.weight: row.selectedOption ? Font.DemiBold : Font.Normal
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }

                    HoverHandler {
                        id: rowHover
                        cursorShape: Qt.PointingHandCursor
                    }

                    TapHandler {
                        onTapped: {
                            if (row.modelData)
                                root.selected(row.modelData.code);
                            languagePopup.close();
                        }
                    }
                }

                Keys.onReturnPressed: function (event) {
                    const option = root.filteredModel[currentIndex];
                    if (option)
                        root.selected(option.code);
                    languagePopup.close();
                    event.accepted = true;
                }

                Keys.onEscapePressed: function (event) {
                    languagePopup.close();
                    event.accepted = true;
                }

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }
            }
        }
    }
}
