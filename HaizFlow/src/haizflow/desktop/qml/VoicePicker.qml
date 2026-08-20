pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Control {
    id: root

    property var model: []
    property string currentValue: ""
    property string activeCategory: ""
    // Batch settings deliberately omit per-video voice cloning: a clone needs
    // one authorised sample and transcript for each source video.
    property bool allowVoiceClone: true
    signal selected(string voice)

    implicitHeight: 42
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: displayLabel()

    function visibleOptions() {
        const result = []
        const source = model || []
        for (let i = 0; i < source.length; ++i) {
            const option = source[i]
            if (allowVoiceClone || String(option.voice || "") !== "omnivoice:clone")
                result.push(option)
        }
        return result
    }

    function categories() {
        const result = []
        const seen = {}
        const options = visibleOptions()
        for (let i = 0; i < options.length; ++i) {
            const key = String(options[i].category || "voices")
            if (!seen[key]) {
                result.push({
                    "key": key,
                    "label": String(options[i].categoryLabel || key),
                    "description": categoryDescription(key),
                    "icon": categoryIcon(key)
                })
                seen[key] = true
            }
        }
        return result
    }

    function voicesIn(category) {
        const result = []
        const options = visibleOptions()
        for (let i = 0; i < options.length; ++i) {
            if (String(options[i].category || "voices") === category)
                result.push(options[i])
        }
        return result
    }

    function categoryIcon(category) {
        if (category === "clone")
            return "\uE8D4"
        if (category === "meme")
            return "\uE790"
        return "\uE8D7"
    }

    function categoryDescription(category) {
        if (category === "clone")
            return I18n.t("Use an authorised reference sample")
        if (category === "meme")
            return I18n.t("Character and expressive voices")
        return I18n.t("Natural voices for your selected language")
    }

    function voiceDescription(option) {
        if (String(option.voice || "") === "omnivoice:clone")
            return I18n.t("Choose a sample and transcript after selecting")
        if (String(option.category || "") === "meme")
            return I18n.t("Creative style — preview before processing")
        return I18n.t("Balanced voice for narration")
    }

    function displayLabel() {
        for (let i = 0; i < model.length; ++i) {
            if (String(model[i].voice || "") === currentValue)
                return String(model[i].label || currentValue)
        }
        return currentValue
    }

    function syncCategory() {
        const options = visibleOptions()
        for (let i = 0; i < options.length; ++i) {
            if (String(options[i].voice || "") === currentValue) {
                activeCategory = String(options[i].category || "voices")
                return
            }
        }
        const available = categories()
        activeCategory = available.length > 0 ? available[0].key : ""
    }

    onModelChanged: syncCategory()
    onCurrentValueChanged: syncCategory()
    onAllowVoiceCloneChanged: syncCategory()
    Component.onCompleted: syncCategory()

    contentItem: RowLayout {
        spacing: Theme.space8
        Text {
            Layout.fillWidth: true
            text: root.displayLabel()
            color: root.enabled ? Theme.text : Theme.textDisabled
            font.pixelSize: Theme.body
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        AppIcon {
            glyph: voicePopup.opened ? "\uE70E" : "\uE70D"
            iconColor: root.enabled ? Theme.textMuted : Theme.textDisabled
            iconSize: Theme.iconSmall
        }
    }

    background: Rectangle {
        color: root.hovered ? Theme.surfaceMuted : Theme.input
        radius: Theme.radiusSmall
        border.width: root.activeFocus || voicePopup.opened ? 2 : 1
        border.color: root.activeFocus || voicePopup.opened ? Theme.focus : Theme.outline
    }

    TapHandler { enabled: root.enabled; onTapped: voicePopup.opened ? voicePopup.close() : voicePopup.open() }
    Keys.onReturnPressed: function(event) {
        voicePopup.opened ? voicePopup.close() : voicePopup.open()
        event.accepted = true
    }
    Keys.onSpacePressed: function(event) {
        voicePopup.opened ? voicePopup.close() : voicePopup.open()
        event.accepted = true
    }

    Popup {
        id: voicePopup
        y: root.height + Theme.space4
        width: Math.max(root.width, 560)
        height: 344
        padding: Theme.space8
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        contentItem: ColumnLayout {
            spacing: Theme.space8

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: I18n.t("Voice library")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                    Text {
                        text: I18n.t("Choose a category, then a voice")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }
                }

                Text {
                    text: root.displayLabel()
                    color: Theme.interactive
                    font.pixelSize: Theme.caption
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.divider
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Theme.space8

                ListView {
                    Layout.preferredWidth: 196
                    Layout.fillHeight: true
                    model: root.categories()
                    clip: true
                    spacing: Theme.space4
                    reuseItems: true
                    delegate: ItemDelegate {
                        id: categoryDelegate
                        required property var modelData
                        width: ListView.view.width
                        height: 58
                        highlighted: String(modelData.key) === root.activeCategory
                        focusPolicy: Qt.NoFocus
                        onClicked: root.activeCategory = String(modelData.key)
                        contentItem: RowLayout {
                            spacing: Theme.space8
                            AppIcon {
                                Layout.preferredWidth: Theme.icon
                                Layout.preferredHeight: Theme.icon
                                glyph: String(categoryDelegate.modelData.icon || "")
                                iconColor: categoryDelegate.highlighted ? Theme.interactive : Theme.textMuted
                                iconSize: Theme.iconSmall
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    Layout.fillWidth: true
                                    text: String(categoryDelegate.modelData.label || "")
                                    color: categoryDelegate.highlighted ? Theme.text : Theme.textMuted
                                    font.pixelSize: Theme.caption
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: String(categoryDelegate.modelData.description || "")
                                    color: Theme.textSubtle
                                    font.pixelSize: Theme.caption - 1
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }
                            }
                        }
                        background: Rectangle {
                            color: categoryDelegate.highlighted ? Theme.interactiveMuted
                                : (categoryDelegate.hovered ? Theme.surfaceMuted : "transparent")
                            radius: Theme.radiusSmall
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    color: Theme.divider
                }

                ListView {
                    id: voiceList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: root.voicesIn(root.activeCategory)
                    clip: true
                    spacing: Theme.space4
                    reuseItems: true
                    delegate: ItemDelegate {
                        id: voiceDelegate
                        required property var modelData
                        width: ListView.view.width
                        height: 58
                        enabled: modelData.available === undefined || modelData.available !== false
                        highlighted: String(modelData.voice || "") === root.currentValue
                        focusPolicy: Qt.NoFocus
                        onClicked: {
                            root.selected(String(modelData.voice || ""))
                            voicePopup.close()
                        }
                        contentItem: RowLayout {
                            spacing: Theme.space8
                            AppIcon {
                                Layout.preferredWidth: Theme.icon
                                Layout.preferredHeight: Theme.icon
                                glyph: String(voiceDelegate.modelData.voice || "") === "omnivoice:clone"
                                    ? "\uE8D4" : "\uE8D7"
                                iconColor: !voiceDelegate.enabled ? Theme.textDisabled
                                    : (voiceDelegate.highlighted ? Theme.interactive : Theme.textMuted)
                                iconSize: Theme.iconSmall
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    Layout.fillWidth: true
                                    text: String(voiceDelegate.modelData.label || voiceDelegate.modelData.voice || "")
                                    color: !voiceDelegate.enabled ? Theme.textDisabled : Theme.text
                                    font.pixelSize: Theme.body
                                    font.weight: voiceDelegate.highlighted ? Font.DemiBold : Font.Medium
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: root.voiceDescription(voiceDelegate.modelData)
                                    color: !voiceDelegate.enabled ? Theme.textDisabled : Theme.textMuted
                                    font.pixelSize: Theme.caption
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }
                            }
                            AppIcon {
                                Layout.preferredWidth: Theme.icon
                                Layout.preferredHeight: Theme.icon
                                visible: voiceDelegate.highlighted
                                glyph: "\uE73E"
                                iconColor: Theme.interactive
                                iconSize: Theme.iconSmall
                            }
                        }
                        background: Rectangle {
                            color: voiceDelegate.highlighted ? Theme.interactiveMuted
                                : (voiceDelegate.hovered ? Theme.surfaceMuted : "transparent")
                            radius: Theme.radiusSmall
                        }
                    }
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                }
            }
        }

        background: Rectangle {
            color: Theme.surfaceElevated
            radius: Theme.radius
            border.width: 1
            border.color: Theme.outlineStrong
        }
    }
}
