pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    required property var downloader
    readonly property bool channelActive: downloader.channelBusy
    readonly property bool hasResults: downloader.channelCandidateCount > 0
    property string selectedPlatform: "youtube"
    readonly property var platformOptions: [
        { "label": "YouTube", "value": "youtube", "platform": "youtube" },
        { "label": "TikTok", "value": "tiktok", "platform": "tiktok" },
        { "label": "Douyin", "value": "douyin", "platform": "douyin" },
        { "label": "Bilibili", "value": "bilibili", "platform": "bilibili" },
        { "label": "Instagram", "value": "instagram", "platform": "instagram" },
        { "label": "Facebook", "value": "facebook", "platform": "facebook" },
        { "label": "X", "value": "x", "platform": "x" },
        { "label": "Vimeo", "value": "vimeo", "platform": "vimeo" },
        { "label": "Dailymotion", "value": "dailymotion", "platform": "dailymotion" },
        { "label": "Twitch", "value": "twitch", "platform": "twitch" },
        { "label": "Reddit", "value": "reddit", "platform": "reddit" },
        { "label": "VK", "value": "vk", "platform": "vk" }
    ]

    function placeholder() {
        if (selectedPlatform === "tiktok")
            return I18n.t("Paste a TikTok profile link")
        if (selectedPlatform === "douyin")
            return I18n.t("Paste a Douyin profile link")
        if (selectedPlatform === "youtube")
            return I18n.t("Paste a YouTube channel link")
        return I18n.t("Paste a public profile or channel link")
    }

    function contentOptions() {
        if (selectedPlatform === "youtube") {
            return [
                { "label": I18n.t("All YouTube videos"), "value": "all" },
                { "label": I18n.t("YouTube Shorts"), "value": "short" },
                { "label": I18n.t("Regular YouTube videos"), "value": "long" }
            ]
        }
        return [{ "label": I18n.t("Public videos"), "value": "all" }]
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space16

        PageHeader {
            Layout.fillWidth: true
            title: I18n.t("Download channel")
            subtitle: I18n.t("Preview public videos from a channel or creator profile before saving")
        }

        ScrollView {
            id: channelScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: channelScroll.availableWidth
                spacing: Theme.space16

                Panel {
                    Layout.fillWidth: true
                    title: I18n.t("Channel source")
                    subtitle: I18n.t("Choose a platform, apply filters, then preview available public videos")

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space4

                        Text {
                            text: I18n.t("Platform")
                            color: Theme.textMuted
                            font.pixelSize: Theme.label
                        }

                        AppComboBox {
                            id: platformSelector
                            Layout.fillWidth: true
                            model: root.platformOptions
                            textRole: "label"
                            valueRole: "value"
                            logoRole: "platform"
                            logoModel: root.platformOptions
                            currentIndex: 0
                            enabled: !root.channelActive
                            Accessible.name: I18n.t("Platform")
                            onActivated: function(index) {
                                root.selectedPlatform = String(platformSelector.model[index].value)
                                contentFilter.currentIndex = 0
                                channelUrl.forceActiveFocus()
                            }
                        }
                    }

                    TextField {
                        id: channelUrl
                        Layout.fillWidth: true
                        implicitHeight: 44
                        placeholderText: root.placeholder()
                        selectByMouse: true
                        activeFocusOnTab: true
                        enabled: !root.channelActive
                        Accessible.name: I18n.t("Channel link")
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: Theme.input
                            border.width: channelUrl.activeFocus ? 2 : 1
                            border.color: channelUrl.activeFocus ? Theme.focus : Theme.outline
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width >= 900 ? 4 : width >= 680 ? 3 : 2
                        columnSpacing: Theme.space12
                        rowSpacing: Theme.space12

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space4
                            Text { text: I18n.t("Order"); color: Theme.textMuted; font.pixelSize: Theme.label }
                            AppComboBox {
                                id: ranking
                                Layout.fillWidth: true
                                model: [{ "label": I18n.t("Newest"), "value": "newest" }, { "label": I18n.t("Most viewed"), "value": "popular" }]
                                textRole: "label"
                                valueRole: "value"
                                enabled: !root.channelActive
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space4
                            Text { text: I18n.t("Download limit"); color: Theme.textMuted; font.pixelSize: Theme.label }
                            AppSpinBox { id: channelLimit; Layout.fillWidth: true; from: 1; to: 100; value: 20; enabled: !root.channelActive }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space4
                            Text { text: I18n.t("Content type"); color: Theme.textMuted; font.pixelSize: Theme.label }
                            AppComboBox {
                                id: contentFilter
                                Layout.fillWidth: true
                                model: root.contentOptions()
                                textRole: "label"
                                valueRole: "value"
                                enabled: !root.channelActive
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            visible: ranking.currentValue === "popular"
                            spacing: Theme.space4
                            Text { text: I18n.t("Scan range"); color: Theme.textMuted; font.pixelSize: Theme.label }
                            AppComboBox {
                                id: scanScope
                                Layout.fillWidth: true
                                model: [
                                    { "label": I18n.t("100 videos"), "value": 100 },
                                    { "label": I18n.t("300 videos"), "value": 300 },
                                    { "label": I18n.t("1000 videos"), "value": 1000 },
                                    { "label": I18n.t("All available"), "value": 0 }
                                ]
                                textRole: "label"
                                valueRole: "value"
                                currentIndex: 1
                                enabled: !root.channelActive
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space12
                        Text {
                            Layout.fillWidth: true
                            text: root.downloader.channelOutputDirectory.length > 0 ? root.downloader.channelOutputDirectory : I18n.t("No channel folder selected")
                            color: root.downloader.channelOutputDirectory.length > 0 ? Theme.text : Theme.textMuted
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                        }
                        AppButton {
                            visible: !root.downloader.outputManaged
                            text: I18n.t("Choose folder")
                            enabled: !root.channelActive
                            onClicked: root.downloader.chooseChannelOutputDirectory()
                        }
                        AppButton {
                            text: root.hasResults ? I18n.t("Scan again") : I18n.t("Preview videos")
                            tone: "primary"
                            enabled: channelUrl.text.trim().length > 0 && !root.channelActive
                            onClicked: root.downloader.inspectChannel(channelUrl.text.trim(), root.selectedPlatform, ranking.currentValue, channelLimit.value, contentFilter.currentValue, ranking.currentValue === "popular" ? scanScope.currentValue : 0)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: root.downloader.channelStatus.length > 0
                        Text {
                            Layout.fillWidth: true
                            text: I18n.channelImportStatus(root.downloader.channelStatus)
                            color: root.downloader.channelState === "error" ? Theme.danger : Theme.textMuted
                            wrapMode: Text.WordWrap
                            textFormat: Text.PlainText
                        }
                        AppButton { visible: root.channelActive; text: I18n.t("Cancel download"); tone: "danger"; onClicked: root.downloader.cancel() }
                    }
                    AppProgressBar { Layout.fillWidth: true; visible: root.channelActive; value: root.downloader.channelProgress }
                }

                Panel {
                    Layout.fillWidth: true
                    visible: root.hasResults
                    title: root.downloader.channelName.length > 0 ? root.downloader.channelName : I18n.t("Channel videos")

                    RowLayout {
                        Layout.fillWidth: true
                        AppCheckBox {
                            text: I18n.t("Select all")
                            checked: root.downloader.channelSelectedCount > 0 && root.downloader.channelSelectedCount === root.downloader.channelSelectableCount
                            enabled: !root.channelActive
                            onToggled: root.downloader.selectAllChannel(checked)
                        }
                        Item { Layout.fillWidth: true }
                        AppButton {
                            text: qsTr("%1 (%2)").arg(I18n.t("Download selected")).arg(root.downloader.channelSelectedCount)
                            tone: "primary"
                            enabled: root.downloader.channelSelectedCount > 0
                                && root.downloader.channelOutputDirectory.length > 0 && !root.channelActive
                            onClicked: root.downloader.downloadSelectedChannel()
                        }
                    }

                    ListView {
                        id: candidateList
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(420, Math.max(112, contentHeight))
                        clip: true
                        model: root.downloader.channelCandidateModel
                        reuseItems: true
                        delegate: ChannelVideoRow {
                            width: candidateList.width
                            downloadedMode: true
                            downloadsEnabled: root.downloader.channelOutputDirectory.length > 0
                            onSelectionChanged: function(selected) { root.downloader.setChannelSelected(index, selected) }
                            onRetryRequested: root.downloader.retryChannelVideo(index)
                        }
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    }
                }

                DownloadQueueStatus { Layout.fillWidth: true; downloader: root.downloader }
            }
        }
    }
}
