pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property bool dropActive: false
    property bool templateReady: false

    function loadTemplate() {
        templateReady = false
        defaultCaption.text = AppController.tiktokDefaultCaption
        defaultHashtags.text = AppController.tiktokDefaultHashtags
        templateReady = true
    }

    Component.onCompleted: loadTemplate()
    onVisibleChanged: {
        if (visible)
            loadTemplate()
    }

    Timer {
        id: templateSaveTimer
        interval: 400
        repeat: false
        onTriggered: AppController.saveTikTokPublishDefaults(
            defaultCaption.text,
            defaultHashtags.text,
            false
        )
    }

    Connections {
        target: AppController

        function onTikTokPublishChanged() {
            if (!defaultCaption.activeFocus && !defaultHashtags.activeFocus)
                root.loadTemplate()
        }
    }

    TikTokPostEditorDialog {
        id: editorDialog
        onSaveRequested: function(row, caption, hashtags) {
            AppController.updateTikTokPublishItem(row, caption, hashtags)
        }
    }

    TikTokProjectSourceDialog {
        id: projectSourceDialog
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space20
        spacing: Theme.space12

        PageHeader {
            Layout.fillWidth: true
            Layout.preferredHeight: 62
            title: AppController.projectName || I18n.t("TikTok publishing")
            subtitle: qsTr("%1 / %2 %3")
                .arg(AppController.tiktokPostedCount)
                .arg(AppController.tiktokPublishCount)
                .arg(I18n.t("posted"))

            AppButton {
                text: I18n.t("Prepare next")
                iconGlyph: "\uE768"
                tone: "primary"
                enabled: AppController.tiktokPublishCount > AppController.tiktokPostedCount
                    && !AppController.tiktokPublishBusy
                onClicked: AppController.prepareNextTikTokPublishItem()
            }

            ProjectHeaderActions {
                projectFolderText: I18n.t("Open project folder")
                projectFolderEnabled: AppController.hasOpenProject
                deleteEnabled: AppController.hasOpenProject && !AppController.tiktokPublishBusy
                onProjectFolderRequested: AppController.openProjectFolder()
                onDeleteRequested: AppController.deleteCurrentProject()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            spacing: Theme.space12

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 72
                Layout.minimumWidth: 390
                radius: Theme.radius
                color: Theme.violetSurface
                border.width: 1
                border.color: Theme.violetOutline

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space12
                    spacing: Theme.space12

                    Rectangle {
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        radius: Theme.radiusSmall
                        color: Theme.violetMuted

                        PlatformLogo {
                            anchors.centerIn: parent
                            width: 26
                            height: 26
                            platform: "tiktok"
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 120
                        spacing: Theme.space4

                        Text {
                            Layout.fillWidth: true
                            text: I18n.t("TikTok account")
                            color: Theme.text
                            font.pixelSize: Theme.caption
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: AppController.tiktokPublishStatus.length > 0
                                ? I18n.tiktokPublishStatus(AppController.tiktokPublishStatus)
                                : I18n.t("Sign in once; Chrome keeps this session for HaizFlow")
                            color: Theme.textMuted
                            font.pixelSize: Theme.label
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                    }

                    AppButton {
                        text: I18n.t("Sign in to TikTok")
                        compact: true
                        tone: "secondary"
                        enabled: !AppController.tiktokPublishBusy
                        onClicked: AppController.prepareTikTokLogin()
                    }

                    IconButton {
                        controlSize: 34
                        glyph: "\uE74D"
                        tone: "danger"
                        toolTipText: I18n.t("Clear login")
                        enabled: !AppController.tiktokPublishBusy
                        onClicked: AppController.clearTikTokLoginSession()
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 72
                Layout.minimumWidth: 490
                radius: Theme.radius
                color: root.dropActive ? Theme.interactiveMuted : Theme.blueSurface
                border.width: root.dropActive ? 2 : 1
                border.color: root.dropActive ? Theme.focus : Theme.blueOutline

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space12
                    spacing: Theme.space8

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 130
                        spacing: Theme.space4

                        Text {
                            Layout.fillWidth: true
                            text: AppController.tiktokPublishBusy
                                ? I18n.t("Adding videos")
                                : root.dropActive ? I18n.t("Release to add videos") : I18n.t("Add videos")
                            color: Theme.text
                            font.pixelSize: Theme.caption
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: I18n.t("Drop files here or choose an import source")
                            color: Theme.textMuted
                            font.pixelSize: Theme.label
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                    }

                    AppButton {
                        text: I18n.t("From files")
                        compact: true
                        tone: "violet"
                        enabled: !AppController.tiktokPublishBusy
                        onClicked: AppController.browseTikTokPublishVideos()
                    }

                    AppButton {
                        text: I18n.t("Folder")
                        compact: true
                        enabled: !AppController.tiktokPublishBusy
                        onClicked: AppController.browseTikTokPublishFolder()
                    }

                    AppButton {
                        text: I18n.t("From projects")
                        compact: true
                        enabled: !AppController.tiktokPublishBusy
                        onClicked: projectSourceDialog.openForSelection()
                    }
                }

                DropArea {
                    anchors.fill: parent
                    keys: ["text/uri-list"]
                    onEntered: function(drag) {
                        if (drag.hasUrls) {
                            root.dropActive = true
                            drag.accept()
                        }
                    }
                    onExited: root.dropActive = false
                    onDropped: function(drop) {
                        root.dropActive = false
                        if (!drop.urls || drop.urls.length === 0)
                            return
                        const paths = []
                        for (let index = 0; index < drop.urls.length; ++index)
                            paths.push(String(drop.urls[index]))
                        AppController.addTikTokPublishVideos(paths)
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 86
            radius: Theme.radius
            color: Theme.blueSurface
            border.width: 1
            border.color: Theme.blueOutline

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space12
                anchors.rightMargin: Theme.space12
                anchors.topMargin: Theme.space8
                anchors.bottomMargin: Theme.space8
                spacing: Theme.space12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4

                    Text {
                        text: I18n.t("Default caption")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        font.weight: Font.Medium
                        textFormat: Text.PlainText
                    }

                    TextField {
                        id: defaultCaption
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        color: Theme.text
                        placeholderText: I18n.t("Caption for newly added videos")
                        font.pixelSize: Theme.caption
                        selectByMouse: true
                        onTextChanged: {
                            if (root.templateReady)
                                templateSaveTimer.restart()
                        }
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: Theme.input
                            border.width: defaultCaption.activeFocus ? 2 : 1
                            border.color: defaultCaption.activeFocus ? Theme.focus : Theme.outline
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

                        Text {
                            Layout.fillWidth: true
                            text: I18n.t("Default hashtags")
                            color: Theme.textMuted
                            font.pixelSize: Theme.label
                            font.weight: Font.Medium
                            textFormat: Text.PlainText
                        }

                        Text {
                            text: I18n.t("New videos inherit this template")
                            color: Theme.textSubtle
                            font.pixelSize: Theme.label
                            textFormat: Text.PlainText
                        }
                    }

                    TextField {
                        id: defaultHashtags
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        color: Theme.text
                        placeholderText: I18n.t("Example: #review #video #fyp")
                        font.pixelSize: Theme.caption
                        selectByMouse: true
                        onTextChanged: {
                            if (root.templateReady)
                                templateSaveTimer.restart()
                        }
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: Theme.input
                            border.width: defaultHashtags.activeFocus ? 2 : 1
                            border.color: defaultHashtags.activeFocus ? Theme.focus : Theme.outline
                        }
                    }
                }

                AppButton {
                    Layout.alignment: Qt.AlignBottom
                    text: I18n.t("Apply to queue")
                    compact: true
                    enabled: AppController.tiktokPublishCount > 0
                    onClicked: AppController.saveTikTokPublishDefaults(
                        defaultCaption.text,
                        defaultHashtags.text,
                        true
                    )
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true

            Text {
                text: I18n.t("Publishing queue")
                color: Theme.text
                font.pixelSize: Theme.h3
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            Item { Layout.fillWidth: true }

            Text {
                text: qsTr("%1 %2").arg(AppController.tiktokPublishCount).arg(I18n.t("videos"))
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
            }
        }

        GridView {
            id: queueGrid

            readonly property int columnCount: Math.max(1, Math.floor((width + Theme.space12) / (224 + Theme.space12)))
            readonly property real cellContentWidth: Math.floor(width / columnCount)
            readonly property real cardWidth: Math.min(236, Math.max(204, cellContentWidth - Theme.space12))
            readonly property real cardHeight: Math.round(cardWidth * 0.5625 + 126)

            Layout.fillWidth: true
            Layout.fillHeight: true
            model: AppController.tiktokPublishModel
            cellWidth: cellContentWidth
            cellHeight: cardHeight + Theme.space12
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            delegate: Item {
                id: queueDelegate

                required property int index
                required property string fileName
                required property string filePath
                required property string caption
                required property string hashtags
                required property string postText
                required property string publishStatus
                required property string publishError
                required property string thumbnailSource

                width: queueGrid.cardWidth
                height: queueGrid.cardHeight

                GridView.onPooled: {
                    visible = false
                    focus = false
                }
                GridView.onReused: {
                    visible = true
                    focus = false
                }

                TikTokPublishCard {
                    anchors.fill: parent
                    index: queueDelegate.index
                    fileName: queueDelegate.fileName
                    filePath: queueDelegate.filePath
                    caption: queueDelegate.caption
                    hashtags: queueDelegate.hashtags
                    postText: queueDelegate.postText
                    publishStatus: queueDelegate.publishStatus
                    publishError: queueDelegate.publishError
                    thumbnailSource: queueDelegate.thumbnailSource
                    onEditRequested: editorDialog.openForItem(
                        queueDelegate.index,
                        queueDelegate.fileName,
                        queueDelegate.caption,
                        queueDelegate.hashtags
                    )
                }
            }

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
        }
    }
}
