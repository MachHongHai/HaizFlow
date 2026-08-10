pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    function savePublishSettings() {
        const privacy = privacyCombo.currentIndex >= 0
            ? String(privacyCombo.model[privacyCombo.currentIndex])
            : AppController.zernioPrivacyLevel
        AppController.saveZernioPublishSettings(
            privacy,
            publishNowCheck.checked,
            commentsCheck.checked,
            duetCheck.checked,
            stitchCheck.checked
        )
    }

    function privacyLabel(value) {
        if (value === "PUBLIC_TO_EVERYONE")
            return I18n.t("Everyone")
        if (value === "MUTUAL_FOLLOW_FRIENDS")
            return I18n.t("Friends")
        if (value === "FOLLOWER_OF_CREATOR")
            return I18n.t("Followers")
        if (value === "SELF_ONLY")
            return I18n.t("Only me")
        return value
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space12

        PageHeader {
            Layout.fillWidth: true
            title: AppController.projectName
            subtitle: qsTr("%1 / %2 %3")
                .arg(AppController.tiktokPostedCount)
                .arg(AppController.tiktokPublishCount)
                .arg(I18n.t("published"))

            AppButton {
                compact: true
                text: AppController.tiktokPublishBusy ? I18n.t("Cancel") : I18n.t("Publish all")
                iconGlyph: AppController.tiktokPublishBusy ? "\uE71A" : "\uE768"
                tone: AppController.tiktokPublishBusy ? "danger" : "primary"
                enabled: AppController.tiktokPublishBusy
                    || (AppController.tiktokPublishCount > 0
                        && AppController.zernioPublishConsentConfirmed)
                onClicked: {
                    if (AppController.tiktokPublishBusy)
                        AppController.cancelTikTokPublishing()
                    else
                        AppController.publishAllTikTokItems()
                }
            }

            ProjectHeaderActions {
                deleteEnabled: !AppController.tiktokPublishBusy
                onProjectFolderRequested: AppController.openProjectFolder()
                onDeleteRequested: AppController.deleteCurrentProject()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 126
            radius: Theme.radius
            color: Theme.violetSurface
            border.width: 1
            border.color: Theme.violetOutline

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.space16
                spacing: Theme.space20

                ColumnLayout {
                    Layout.preferredWidth: 280
                    Layout.fillHeight: true
                    spacing: Theme.space8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

                        Rectangle {
                            Layout.preferredWidth: 34
                            Layout.preferredHeight: 34
                            radius: Theme.radiusSmall
                            color: Theme.violetMuted

                            AppIcon {
                                anchors.centerIn: parent
                                glyph: "\uE72E"
                                iconColor: Theme.violet
                                iconSize: Theme.icon
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1

                            Text {
                                text: I18n.t("Zernio connection")
                                color: Theme.text
                                font.pixelSize: Theme.body
                                font.weight: Font.DemiBold
                                textFormat: Text.PlainText
                            }

                            Text {
                                Layout.fillWidth: true
                                text: AppController.zernioApiKeyConfigured
                                    ? I18n.t("API key stored securely")
                                    : I18n.t("API key required")
                                color: AppController.zernioApiKeyConfigured ? Theme.success : Theme.warning
                                font.pixelSize: Theme.label
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

                        AppButton {
                            compact: true
                            text: I18n.t("API key")
                            onClicked: apiKeyDialog.openForConfiguration()
                        }

                        AppButton {
                            compact: true
                            text: I18n.t("Connect TikTok")
                            enabled: AppController.zernioApiKeyConfigured && !AppController.tiktokPublishBusy
                            onClicked: AppController.connectZernioTikTok()
                        }

                        IconButton {
                            controlSize: 34
                            glyph: "\uE72C"
                            toolTipText: I18n.t("Refresh accounts")
                            enabled: AppController.zernioApiKeyConfigured && !AppController.tiktokPublishBusy
                            onClicked: AppController.refreshZernioTikTokAccounts()
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    color: Theme.violetOutline
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: Theme.space8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space12

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space4

                            Text {
                                text: I18n.t("TikTok account")
                                color: Theme.textMuted
                                font.pixelSize: Theme.label
                                textFormat: Text.PlainText
                            }

                            AppComboBox {
                                id: accountCombo
                                Layout.fillWidth: true
                                model: AppController.zernioTikTokAccounts
                                enabled: count > 0 && !AppController.tiktokPublishBusy
                                displayText: currentIndex >= 0 ? textAt(currentIndex) : I18n.t("No connected account")
                                onActivated: function(index) { AppController.selectZernioTikTokAccount(index) }
                                Binding {
                                    target: accountCombo
                                    property: "currentIndex"
                                    value: AppController.zernioSelectedAccountIndex
                                }
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space4

                            Text {
                                text: I18n.t("Privacy")
                                color: Theme.textMuted
                                font.pixelSize: Theme.label
                                textFormat: Text.PlainText
                            }

                            AppComboBox {
                                id: privacyCombo
                                Layout.fillWidth: true
                                model: AppController.zernioPrivacyLevels
                                enabled: count > 0 && !AppController.tiktokPublishBusy
                                displayText: currentIndex >= 0
                                    ? root.privacyLabel(String(model[currentIndex]))
                                    : I18n.t("Not available")
                                delegate: ItemDelegate {
                                    id: privacyDelegate
                                    required property int index
                                    width: privacyCombo.popup.width - 12
                                    height: 40
                                    contentItem: Text {
                                        text: root.privacyLabel(String(privacyCombo.model[privacyDelegate.index]))
                                        color: Theme.text
                                        font.pixelSize: Theme.body
                                        verticalAlignment: Text.AlignVCenter
                                        textFormat: Text.PlainText
                                    }
                                    background: Rectangle {
                                        radius: Theme.radiusSmall
                                        color: privacyDelegate.highlighted ? Theme.interactiveMuted : "transparent"
                                    }
                                }
                                onActivated: function(index) {
                                    AppController.saveZernioPublishSettings(
                                        String(model[index]),
                                        AppController.zernioPublishNow,
                                        AppController.zernioAllowComment,
                                        AppController.zernioAllowDuet,
                                        AppController.zernioAllowStitch
                                    )
                                }
                                Binding {
                                    target: privacyCombo
                                    property: "currentIndex"
                                    value: AppController.zernioPrivacyLevels.indexOf(AppController.zernioPrivacyLevel)
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space16

                        AppCheckBox {
                            id: publishNowCheck
                            text: I18n.t("Publish immediately")
                            enabled: !AppController.tiktokPublishBusy
                            onToggled: root.savePublishSettings()
                            Binding { target: publishNowCheck; property: "checked"; value: AppController.zernioPublishNow }
                        }
                        AppCheckBox {
                            id: commentsCheck
                            text: I18n.t("Comments")
                            enabled: !AppController.tiktokPublishBusy
                            onToggled: root.savePublishSettings()
                            Binding { target: commentsCheck; property: "checked"; value: AppController.zernioAllowComment }
                        }
                        AppCheckBox {
                            id: duetCheck
                            text: I18n.t("Duet")
                            enabled: !AppController.tiktokPublishBusy
                            onToggled: root.savePublishSettings()
                            Binding { target: duetCheck; property: "checked"; value: AppController.zernioAllowDuet }
                        }
                        AppCheckBox {
                            id: stitchCheck
                            text: I18n.t("Stitch")
                            enabled: !AppController.tiktokPublishBusy
                            onToggled: root.savePublishSettings()
                            Binding { target: stitchCheck; property: "checked"; value: AppController.zernioAllowStitch }
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 100
            radius: Theme.radius
            color: Theme.blueSurface
            border.width: 1
            border.color: Theme.blueOutline

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.space16
                spacing: Theme.space16

                ColumnLayout {
                    Layout.preferredWidth: 260
                    spacing: Theme.space4

                    Text {
                        text: I18n.t("Add videos")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Files are copied into this project before upload")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                    }
                }

                AppButton {
                    compact: true
                    text: I18n.t("Files")
                    iconGlyph: "\uE8B7"
                    enabled: !AppController.tiktokPublishBusy
                    onClicked: AppController.browseTikTokPublishVideos()
                }
                AppButton {
                    compact: true
                    text: I18n.t("Folder")
                    iconGlyph: "\uE8B7"
                    enabled: !AppController.tiktokPublishBusy
                    onClicked: AppController.browseTikTokPublishFolder()
                }
                AppButton {
                    compact: true
                    text: I18n.t("From projects")
                    iconGlyph: "\uE8A7"
                    enabled: !AppController.tiktokPublishBusy
                    onClicked: projectSourceDialog.openForSelection()
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    color: Theme.blueOutline
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4

                    Text {
                        text: I18n.t("Default post text")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                    Text {
                        Layout.fillWidth: true
                        text: AppController.tiktokDefaultCaption.length > 0 || AppController.tiktokDefaultHashtags.length > 0
                            ? (AppController.tiktokDefaultCaption + " " + AppController.tiktokDefaultHashtags).trim()
                            : I18n.t("No default caption or hashtags")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                }

                AppButton {
                    compact: true
                    text: I18n.t("Edit defaults")
                    onClicked: defaultsDialog.openForDefaults()
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            Text {
                Layout.fillWidth: true
                text: I18n.t("Publishing queue")
                color: Theme.text
                font.pixelSize: Theme.h2
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            Text {
                Layout.maximumWidth: 520
                text: AppController.tiktokPublishStatus
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
                elide: Text.ElideRight
                visible: text.length > 0
            }

            AppCheckBox {
                id: consentCheck
                text: I18n.t("I reviewed the posts and consent to upload")
                enabled: !AppController.tiktokPublishBusy && AppController.tiktokPublishCount > 0
                onToggled: AppController.setZernioPublishConsent(checked)
                Binding {
                    target: consentCheck
                    property: "checked"
                    value: AppController.zernioPublishConsentConfirmed
                }
            }

            AppButton {
                compact: true
                text: I18n.t("Refresh status")
                iconGlyph: "\uE72C"
                enabled: !AppController.tiktokPublishBusy && AppController.tiktokPublishCount > 0
                onClicked: AppController.refreshTikTokPostStatuses()
            }
        }

        GridView {
            id: queueGrid
            readonly property int columnCount: Math.max(1, Math.floor((width + Theme.space16) / (220 + Theme.space16)))
            readonly property real cellContentWidth: Math.floor(width / columnCount)

            Layout.fillWidth: true
            Layout.fillHeight: true
            model: AppController.tiktokPublishModel
            cellWidth: cellContentWidth
            cellHeight: 288
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            delegate: Item {
                id: queueDelegate
                required property int index
                required property string fileName
                required property string caption
                required property string hashtags
                required property string postText
                required property string publishStatus
                required property string publishError
                required property string thumbnailSource
                required property int uploadProgress
                required property string zernioPostId
                required property string platformPostUrl

                width: queueGrid.cellWidth
                height: queueGrid.cellHeight

                GridView.onPooled: {
                    visible = false
                    focus = false
                }
                GridView.onReused: {
                    visible = true
                    focus = false
                }

                TikTokPublishCard {
                    anchors.left: parent.left
                    width: Math.min(220, parent.width - Theme.space16)
                    index: queueDelegate.index
                    fileName: queueDelegate.fileName
                    caption: queueDelegate.caption
                    hashtags: queueDelegate.hashtags
                    postText: queueDelegate.postText
                    publishStatus: queueDelegate.publishStatus
                    publishError: queueDelegate.publishError
                    thumbnailSource: queueDelegate.thumbnailSource
                    uploadProgress: queueDelegate.uploadProgress
                    zernioPostId: queueDelegate.zernioPostId
                    platformPostUrl: queueDelegate.platformPostUrl
                    onEditRequested: postEditor.openForItem(
                        queueDelegate.index,
                        queueDelegate.fileName,
                        queueDelegate.caption,
                        queueDelegate.hashtags
                    )
                }
            }

            Text {
                anchors.centerIn: parent
                visible: queueGrid.count === 0
                text: I18n.t("Add videos to start a TikTok publishing queue")
                color: Theme.textMuted
                font.pixelSize: Theme.body
                textFormat: Text.PlainText
            }

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }
    }

    TikTokProjectSourceDialog { id: projectSourceDialog }

    TikTokPostEditorDialog {
        id: postEditor
        onSaveRequested: function(row, caption, hashtags) {
            AppController.updateTikTokPublishItem(row, caption, hashtags)
        }
    }

    Dialog {
        id: apiKeyDialog
        modal: true
        focus: true
        parent: Overlay.overlay
        width: Math.min(560, parent ? parent.width - 48 : 560)
        height: 330
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        padding: Theme.space24
        title: I18n.t("Zernio API key")
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        function openForConfiguration() {
            apiKeyInput.clear()
            open()
        }

        background: Rectangle {
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.outlineStrong
        }

        contentItem: ColumnLayout {
            spacing: Theme.space12

            Text {
                Layout.fillWidth: true
                text: I18n.t("Create an API key in Zernio, then store it securely for this Windows user.")
                color: Theme.textMuted
                font.pixelSize: Theme.body
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }

            TextField {
                id: apiKeyInput
                Layout.fillWidth: true
                implicitHeight: 44
                echoMode: TextInput.Password
                placeholderText: "sk_..."
                color: Theme.text
                selectByMouse: true
                background: Rectangle {
                    radius: Theme.radiusSmall
                    color: Theme.input
                    border.width: apiKeyInput.activeFocus ? 2 : 1
                    border.color: apiKeyInput.activeFocus ? Theme.focus : Theme.outline
                }
            }

            Text {
                Layout.fillWidth: true
                text: I18n.t("Publishing is not local-only: selected videos are uploaded to Zernio and TikTok.")
                color: Theme.warning
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                AppButton {
                    text: I18n.t("Open Zernio")
                    tone: "ghost"
                    onClicked: AppController.openExternalUrl("https://zernio.com/dashboard")
                }
                AppButton {
                    text: I18n.t("Remove key")
                    tone: "danger"
                    enabled: AppController.zernioApiKeyConfigured && !AppController.tiktokPublishBusy
                    onClicked: {
                        if (AppController.clearZernioApiKey())
                            apiKeyDialog.close()
                    }
                }
                Item { Layout.fillWidth: true }
                AppButton {
                    text: I18n.t("Cancel")
                    tone: "ghost"
                    onClicked: apiKeyDialog.close()
                }
                AppButton {
                    text: I18n.t("Save")
                    tone: "primary"
                    enabled: apiKeyInput.text.trim().length > 0 && !AppController.tiktokPublishBusy
                    onClicked: {
                        if (AppController.saveZernioApiKey(apiKeyInput.text.trim())) {
                            apiKeyInput.clear()
                            apiKeyDialog.close()
                        }
                    }
                }
            }
        }
    }

    Dialog {
        id: defaultsDialog
        modal: true
        focus: true
        parent: Overlay.overlay
        width: Math.min(620, parent ? parent.width - 48 : 620)
        height: 430
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        padding: Theme.space24
        title: I18n.t("Default post text")
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        function openForDefaults() {
            defaultCaption.text = AppController.tiktokDefaultCaption
            defaultHashtags.text = AppController.tiktokDefaultHashtags
            applyExisting.checked = false
            open()
        }

        background: Rectangle {
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.outlineStrong
        }

        contentItem: ColumnLayout {
            spacing: Theme.space12

            Text { text: I18n.t("Caption"); color: Theme.textMuted; font.pixelSize: Theme.caption }
            TextArea {
                id: defaultCaption
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 120
                color: Theme.text
                wrapMode: TextEdit.Wrap
                selectByMouse: true
                background: Rectangle {
                    radius: Theme.radiusSmall
                    color: Theme.input
                    border.width: defaultCaption.activeFocus ? 2 : 1
                    border.color: defaultCaption.activeFocus ? Theme.focus : Theme.outline
                }
            }
            Text { text: I18n.t("Hashtags"); color: Theme.textMuted; font.pixelSize: Theme.caption }
            TextField {
                id: defaultHashtags
                Layout.fillWidth: true
                implicitHeight: 44
                color: Theme.text
                placeholderText: "#video #fyp"
                selectByMouse: true
                background: Rectangle {
                    radius: Theme.radiusSmall
                    color: Theme.input
                    border.width: defaultHashtags.activeFocus ? 2 : 1
                    border.color: defaultHashtags.activeFocus ? Theme.focus : Theme.outline
                }
            }
            AppCheckBox {
                id: applyExisting
                text: I18n.t("Apply to videos waiting in the queue")
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton { text: I18n.t("Cancel"); tone: "ghost"; onClicked: defaultsDialog.close() }
                AppButton {
                    text: I18n.t("Save")
                    tone: "primary"
                    onClicked: {
                        if (AppController.saveTikTokPublishDefaults(
                                defaultCaption.text, defaultHashtags.text, applyExisting.checked))
                            defaultsDialog.close()
                    }
                }
            }
        }
    }
}
