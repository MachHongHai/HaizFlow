pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    function confirmPublish(row, publishAll) {
        publishConfirmation.itemRow = row
        publishConfirmation.publishAllItems = publishAll
        publishConfirmation.open()
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
                        && AppController.zernioApiKeyVerified
                        && AppController.zernioAccountReady
                        && !AppController.zernioAccountSyncing)
                onClicked: {
                    if (AppController.tiktokPublishBusy)
                        AppController.cancelTikTokPublishing()
                    else
                        root.confirmPublish(-1, true)
                }
            }

            ProjectHeaderActions {
                deleteEnabled: !AppController.tiktokPublishBusy
                onProjectFolderRequested: AppController.openProjectFolder()
                onDeleteRequested: AppController.deleteCurrentProject()
            }
        }

        ZernioAccessPanel {
            Layout.fillWidth: true
            Layout.minimumHeight: 56
            Layout.preferredHeight: 56
            Layout.maximumHeight: 56
            onSetupGuideRequested: zernioGuide.open()
            onApiKeyManagementRequested: apiKeyDialog.openForConfiguration()
        }

        ZernioSetupPanel {
            id: zernioSetupPanel

            Layout.fillWidth: true
            Layout.minimumHeight: 56
            Layout.preferredHeight: 56
            Layout.maximumHeight: 56
            onConnectionPickerRequested: connectionDialog.openForSelection()
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.minimumHeight: 66
            Layout.preferredHeight: 66
            Layout.maximumHeight: 66
            radius: Theme.radius
            color: Theme.surfaceMuted
            border.width: 1
            border.color: Theme.outlineStrong

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.space12
                spacing: Theme.space12

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 3
                    spacing: 1

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Default post text")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: AppController.tiktokDefaultCaption.length > 0 || AppController.tiktokDefaultHashtags.length > 0
                            ? (AppController.tiktokDefaultCaption + "  " + AppController.tiktokDefaultHashtags).trim()
                            : I18n.t("No caption or hashtags")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                }

                AppButton {
                    compact: true
                    text: I18n.t("Edit content")
                    onClicked: defaultsDialog.openForDefaults()
                }

                AppButton {
                    compact: true
                    text: I18n.t("Post options")
                    iconGlyph: "\uE713"
                    enabled: zernioSetupPanel.setupComplete && !AppController.tiktokPublishBusy
                    onClicked: zernioSetupPanel.openPostOptions()
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 36
                    color: Theme.outline
                }

                Text {
                    text: I18n.t("Video sources")
                    color: Theme.text
                    font.pixelSize: Theme.body
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                AppButton {
                    id: addVideosButton
                    property bool menuWasOpenOnPress: false

                    compact: true
                    text: I18n.t("Add videos")
                    iconGlyph: "\uE710"
                    tone: "primary"
                    enabled: !AppController.tiktokPublishBusy
                    onPressed: menuWasOpenOnPress = addSourceMenu.visible
                    onClicked: {
                        if (menuWasOpenOnPress || addSourceMenu.visible)
                            addSourceMenu.close()
                        else
                            addSourceMenu.open()
                    }

                    Menu {
                        id: addSourceMenu
                        width: 210
                        x: parent.width - width
                        y: parent.height + Theme.space4
                        padding: Theme.space4
                        closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside

                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: Theme.surfaceElevated
                            border.width: 1
                            border.color: Theme.outlineStrong
                        }

                        AppMenuItem {
                            text: I18n.t("From files")
                            iconGlyph: "\uE8B7"
                            onTriggered: AppController.browseSocialPublishVideos()
                        }
                        AppMenuItem {
                            text: I18n.t("From folder")
                            iconGlyph: "\uE8B7"
                            onTriggered: AppController.browseSocialPublishFolder()
                        }
                        AppMenuItem {
                            text: I18n.t("Add from projects")
                            iconGlyph: "\uE7C3"
                            onTriggered: projectSourceDialog.openForSelection()
                        }
                    }
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
                visible: AppController.tiktokPublishBusy && text.length > 0
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
                required property bool platformPostUrlVerified
                required property string targetPlatform

                width: queueGrid.cellWidth
                height: queueGrid.cellHeight

                GridView.onPooled: {
                    publishCard.resetReusableState()
                    visible = false
                    focus = false
                }
                GridView.onReused: {
                    publishCard.resetReusableState()
                    visible = true
                    focus = false
                }

                SocialPublishCard {
                    id: publishCard
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
                    platformPostUrlVerified: queueDelegate.platformPostUrlVerified
                    targetPlatform: queueDelegate.targetPlatform
                    onPublishRequested: root.confirmPublish(queueDelegate.index, false)
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
                text: I18n.t("Add videos to start a social publishing queue")
                color: Theme.textMuted
                font.pixelSize: Theme.body
                textFormat: Text.PlainText
            }

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }
    }

    SocialProjectSourceDialog { id: projectSourceDialog }

    SocialPostEditorDialog {
        id: postEditor
        onSaveRequested: function(row, caption, hashtags) {
            AppController.updateTikTokPublishItem(row, caption, hashtags)
        }
    }

    ZernioGuideDialog {
        id: zernioGuide
        onConfigureApiKeyRequested: {
            close()
            Qt.callLater(apiKeyDialog.openForConfiguration)
        }
        onChooseConnectionRequested: {
            close()
            Qt.callLater(connectionDialog.openForSelection)
        }
    }

    ZernioConnectionDialog { id: connectionDialog }

    ZernioApiKeyDialog { id: apiKeyDialog }

    Dialog {
        id: publishConfirmation

        property int itemRow: -1
        property bool publishAllItems: false

        modal: true
        focus: true
        parent: Overlay.overlay
        width: Math.min(460, parent ? parent.width - 48 : 460)
        height: 260
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        padding: Theme.space24
        title: I18n.t("Confirm upload")
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.outlineStrong
        }

        contentItem: ColumnLayout {
            spacing: Theme.space16

            Text {
                Layout.fillWidth: true
                text: publishConfirmation.publishAllItems
                    ? I18n.t("Upload all waiting videos?")
                    : I18n.t("Upload this video?")
                color: Theme.text
                font.pixelSize: Theme.h3
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                PlatformLogo {
                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 22
                    platform: AppController.zernioSelectedPlatform
                }
                Text {
                    Layout.fillWidth: true
                    text: AppController.zernioSelectedAccountName
                    color: Theme.textMuted
                    font.pixelSize: Theme.body
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
            }
            Text {
                Layout.fillWidth: true
                text: I18n.t("The video will be uploaded to Zernio and the selected platform.")
                color: Theme.textMuted
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton {
                    compact: true
                    tone: "ghost"
                    text: I18n.t("Cancel")
                    onClicked: publishConfirmation.close()
                }
                AppButton {
                    compact: true
                    tone: "primary"
                    text: I18n.t("Upload")
                    onClicked: {
                        AppController.setZernioPublishConsent(true)
                        if (publishConfirmation.publishAllItems)
                            AppController.publishAllTikTokItems()
                        else
                            AppController.publishTikTokItem(publishConfirmation.itemRow)
                        publishConfirmation.close()
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
            applyExisting.checked = true
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
