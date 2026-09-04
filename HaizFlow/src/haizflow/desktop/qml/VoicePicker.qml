pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "."

Control {
    id: root

    property var model: []
    property string currentValue: ""
    property string activeCategory: ""
    property bool allowVoiceClone: false
    property bool previewEnabled: true
    property string previewSource: ""
    property string previewState: "idle"
    property string requestedVoice: ""
    signal selected(string voice)
    signal previewRequested(string voice)

    implicitHeight: 42
    leftPadding: Theme.space12
    rightPadding: Theme.space12
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
                    "label": String(options[i].categoryLabel || key)
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

    function displayLabel() {
        if (currentValue === "omnivoice:clone")
            return qsTr("Giọng đã nhân bản")
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

    function togglePreview(voice) {
        if (!previewEnabled)
            return
        const value = String(voice || "")
        if (requestedVoice === value && previewState === "ready") {
            if (voicePlayer.playbackState === MediaPlayer.PlayingState)
                voicePlayer.pause()
            else
                voicePlayer.play()
            return
        }
        voicePlayer.stop()
        requestedVoice = value
        previewRequested(value)
    }

    function playPreparedPreview() {
        if (requestedVoice.length > 0 && previewState === "ready" && previewSource.length > 0) {
            voicePlayer.source = previewSource
            voicePlayer.play()
        }
    }

    onModelChanged: syncCategory()
    onCurrentValueChanged: syncCategory()
    onAllowVoiceCloneChanged: syncCategory()
    onPreviewEnabledChanged: if (!previewEnabled) voicePlayer.stop()
    Component.onCompleted: syncCategory()
    onPreviewStateChanged: previewStartTimer.restart()
    onPreviewSourceChanged: previewStartTimer.restart()

    Timer {
        id: previewStartTimer
        interval: 0
        repeat: false
        onTriggered: root.playPreparedPreview()
    }

    AudioOutput {
        id: voicePreviewOutput
        volume: 1.0
    }

    MediaPlayer {
        id: voicePlayer
        audioOutput: voicePreviewOutput
        onMediaStatusChanged: function() {
            if (voicePlayer.mediaStatus === MediaPlayer.EndOfMedia)
                voicePlayer.stop()
        }
    }

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
        objectName: "voicePickerPopup"
        parent: Overlay.overlay
        modal: false
        focus: true
        margins: Theme.space8
        width: Math.max(280, Math.min(Math.max(root.width, 520), parent.width - Theme.space16))
        height: Math.min(330, parent.height - Theme.space16,
            126 + Math.max(1, voiceList.count) * 46)
        x: {
            const point = root.mapToItem(parent, 0, 0)
            return Math.max(
                Theme.space8,
                Math.min(point.x + root.width - width, parent.width - width - Theme.space8)
            )
        }
        y: {
            const point = root.mapToItem(parent, 0, 0)
            const below = point.y + root.height + Theme.space4
            if (below + height <= parent.height - Theme.space8)
                return below
            return Math.max(Theme.space8, point.y - height - Theme.space4)
        }
        padding: Theme.space8
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onClosed: {
            voicePlayer.stop()
            root.requestedVoice = ""
        }

        contentItem: ColumnLayout {
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Giọng đọc")
                    color: Theme.text
                    font.pixelSize: Theme.body
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
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

            ListView {
                id: categoryList
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                orientation: ListView.Horizontal
                model: root.categories()
                clip: true
                spacing: Theme.space4
                reuseItems: true
                delegate: ItemDelegate {
                    id: categoryDelegate
                    required property var modelData
                    width: Math.max(92, categoryLabel.implicitWidth + Theme.space12 * 2)
                    height: 36
                    highlighted: String(modelData.key) === root.activeCategory
                    focusPolicy: Qt.NoFocus
                    onClicked: root.activeCategory = String(modelData.key)
                    contentItem: RowLayout {
                        Text {
                            id: categoryLabel
                            Layout.fillWidth: true
                            text: String(categoryDelegate.modelData.label || "")
                            color: categoryDelegate.highlighted ? Theme.text : Theme.textMuted
                            font.pixelSize: Theme.caption
                            font.weight: categoryDelegate.highlighted ? Font.DemiBold : Font.Medium
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }
                    }
                    background: Rectangle {
                        color: categoryDelegate.highlighted ? Theme.interactiveMuted
                            : (categoryDelegate.hovered ? Theme.surfaceMuted : "transparent")
                        radius: Theme.radiusSmall
                    }
                }
                ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
            }

            ListView {
                id: voiceList
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: root.voicesIn(root.activeCategory)
                clip: true
                spacing: 2
                reuseItems: true
                delegate: ItemDelegate {
                    id: voiceDelegate
                    required property var modelData
                    width: ListView.view.width
                    height: 44
                    enabled: modelData.available === undefined || modelData.available !== false
                    highlighted: String(modelData.voice || "") === root.currentValue
                    focusPolicy: Qt.NoFocus
                    onClicked: {
                        root.selected(String(modelData.voice || ""))
                        voicePopup.close()
                    }
                    contentItem: RowLayout {
                        spacing: Theme.space8
                        Text {
                            Layout.fillWidth: true
                            text: String(voiceDelegate.modelData.label || voiceDelegate.modelData.voice || "")
                            color: !voiceDelegate.enabled ? Theme.textDisabled : Theme.text
                            font.pixelSize: Theme.body
                            font.weight: voiceDelegate.highlighted ? Font.DemiBold : Font.Normal
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }
                        AppIcon {
                            visible: voiceDelegate.highlighted
                            glyph: "\uE73E"
                            iconColor: Theme.interactive
                            iconSize: Theme.iconSmall
                        }
                        Item {
                            visible: root.previewEnabled
                            Layout.preferredWidth: visible ? 30 : 0
                            Layout.preferredHeight: 30

                            StudioIconButton {
                                anchors.fill: parent
                                visible: !(root.requestedVoice === String(voiceDelegate.modelData.voice || "")
                                    && root.previewState === "preparing")
                                enabled: voiceDelegate.enabled
                                    && (voiceDelegate.modelData.previewAvailable === undefined
                                        || voiceDelegate.modelData.previewAvailable === true)
                                iconName: root.requestedVoice === String(voiceDelegate.modelData.voice || "")
                                    && voicePlayer.playbackState === MediaPlayer.PlayingState ? "pause" : "play"
                                toolTipText: !enabled ? qsTr("Chưa có bản nghe thử")
                                    : root.requestedVoice === String(voiceDelegate.modelData.voice || "")
                                        && voicePlayer.playbackState === MediaPlayer.PlayingState
                                        ? qsTr("Tạm dừng nghe thử") : qsTr("Nghe thử giọng")
                                onClicked: root.togglePreview(String(voiceDelegate.modelData.voice || ""))
                            }

                            BusyIndicator {
                                anchors.centerIn: parent
                                width: 18
                                height: 18
                                running: visible
                                visible: root.requestedVoice === String(voiceDelegate.modelData.voice || "")
                                    && root.previewState === "preparing"
                                Accessible.name: qsTr("Đang tạo bản nghe thử")
                            }
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

        background: Rectangle {
            color: Theme.surfaceElevated
            radius: Theme.radius
            border.width: 1
            border.color: Theme.outlineStrong
        }
    }
}
