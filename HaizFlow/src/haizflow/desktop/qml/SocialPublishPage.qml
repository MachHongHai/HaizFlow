pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    function confirmPublish(row, publishAll) {
        publishConfirmationLoader.invoke("openForPublish", [row, publishAll])
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
                .arg(qsTr("đã đăng"))

            AppButton {
                compact: true
                text: AppController.tiktokPublishBusy ? qsTr("Hủy") : qsTr("Đăng tất cả")
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

        SocialConnectionBar {
            id: zernioSetupPanel
            Layout.fillWidth: true
            onSetupGuideRequested: zernioGuideLoader.invoke("open", [])
            onApiKeyManagementRequested: apiKeyDialogLoader.invoke("openForConfiguration", [])
            onConnectionPickerRequested: connectionDialogLoader.invoke("openForSelection", [])
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 58
            radius: Theme.radiusSmall
            color: Theme.surface
            border.width: 1
            border.color: Theme.outline

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.space12
                spacing: Theme.space12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Nội dung mặc định")
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.control
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: AppController.tiktokDefaultCaption.length > 0 || AppController.tiktokDefaultHashtags.length > 0
                            ? (AppController.tiktokDefaultCaption + "  " + AppController.tiktokDefaultHashtags).trim()
                            : qsTr("Chưa có nội dung hoặc hashtag")
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.label
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                }

                AppButton {
                    compact: true
                    text: qsTr("Chỉnh nội dung")
                    onClicked: defaultsDialogLoader.invoke("openForDefaults", [])
                }

                AppButton {
                    compact: true
                    text: qsTr("Tùy chọn bài đăng")
                    iconGlyph: "\uE713"
                    enabled: zernioSetupPanel.setupComplete && !AppController.tiktokPublishBusy
                    onClicked: zernioSetupPanel.openPostOptions()
                }

            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            radius: Theme.radiusSmall
            color: Theme.surface
            border.width: 1
            border.color: Theme.outline

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space12
                anchors.rightMargin: Theme.space12
                spacing: Theme.space12

                FluentIcon {
                    Layout.preferredWidth: 18
                    Layout.preferredHeight: 18
                    name: "video"
                    iconColor: Theme.interactive
                    iconSize: 17
                }
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Nguồn video")
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.control
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                AppButton {
                    id: addVideosButton
                    property bool menuWasOpenOnPress: false

                    compact: true
                    text: qsTr("Thêm video")
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
                            text: qsTr("Từ tệp")
                            iconGlyph: "\uE8B7"
                            onTriggered: AppController.browseSocialPublishVideos()
                        }
                        AppMenuItem {
                            text: qsTr("Từ thư mục")
                            iconGlyph: "\uE8B7"
                            onTriggered: AppController.browseSocialPublishFolder()
                        }
                        AppMenuItem {
                            text: qsTr("Từ dự án")
                            iconGlyph: "\uE7C3"
                            onTriggered: projectSourceDialogLoader.invoke("openForSelection", [])
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
                text: qsTr("Hàng đợi đăng")
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

        AppSurface {
            Layout.fillWidth: true
            Layout.fillHeight: true
            padding: 0

            ListView {
                id: queueList
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: AppController.tiktokPublishModel
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: true

                delegate: SocialPublishRow {
                    width: queueList.width
                    onPublishRequested: root.confirmPublish(index, false)
                    onEditRequested: postEditorLoader.invoke("openForItem", [index, fileName, caption, hashtags])
                }

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }

            Text {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: queueList.count === 0
                text: qsTr("Thêm video vào hàng đợi đăng.")
                color: Theme.textMuted
                font.pixelSize: TypeScale.control
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                textFormat: Text.PlainText
            }
        }
    }

    LazyDialogLoader {
        id: projectSourceDialogLoader
        sourceComponent: Component {
            SocialProjectSourceDialog { onClosed: projectSourceDialogLoader.release() }
        }
    }

    LazyDialogLoader {
        id: postEditorLoader
        sourceComponent: Component {
            SocialPostEditorDialog {
                onClosed: postEditorLoader.release()
                onSaveRequested: function(row, caption, hashtags) {
                    AppController.updateTikTokPublishItem(row, caption, hashtags)
                }
            }
        }
    }

    LazyDialogLoader {
        id: zernioGuideLoader
        sourceComponent: Component {
            ZernioGuideDialog {
                onClosed: zernioGuideLoader.release()
                onConfigureApiKeyRequested: {
                    close()
                    apiKeyDialogLoader.invoke("openForConfiguration", [])
                }
                onChooseConnectionRequested: {
                    close()
                    connectionDialogLoader.invoke("openForSelection", [])
                }
            }
        }
    }

    LazyDialogLoader {
        id: connectionDialogLoader
        sourceComponent: Component {
            ZernioConnectionDialog { onClosed: connectionDialogLoader.release() }
        }
    }

    LazyDialogLoader {
        id: apiKeyDialogLoader
        sourceComponent: Component {
            ZernioApiKeyDialog { onClosed: apiKeyDialogLoader.release() }
        }
    }

    LazyDialogLoader {
        id: publishConfirmationLoader
        sourceComponent: Component {
            SocialPublishConfirmDialog { onClosed: publishConfirmationLoader.release() }
        }
    }

    LazyDialogLoader {
        id: defaultsDialogLoader
        sourceComponent: Component {
            SocialDefaultsDialog { onClosed: defaultsDialogLoader.release() }
        }
    }
}
