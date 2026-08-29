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
            return qsTr("Dán liên kết trang cá nhân TikTok")
        if (selectedPlatform === "douyin")
            return qsTr("Dán liên kết trang cá nhân Douyin")
        if (selectedPlatform === "youtube")
            return qsTr("Dán liên kết kênh YouTube")
        return qsTr("Dán liên kết hồ sơ hoặc kênh công khai")
    }

    function contentOptions() {
        if (selectedPlatform === "youtube") {
            return [
                { "label": qsTr("Tất cả video YouTube"), "value": "all" },
                { "label": qsTr("YouTube Shorts"), "value": "short" },
                { "label": qsTr("Video YouTube thường"), "value": "long" }
            ]
        }
        return [{ "label": qsTr("Video công khai"), "value": "all" }]
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space16

        ScrollView {
            id: channelScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: channelScroll.availableWidth
                spacing: Theme.space16

                AppSurface {
                    Layout.fillWidth: true
                    padding: Theme.space16

                    SectionHeader {
                        Layout.fillWidth: true
                        title: qsTr("Nguồn kênh")
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space4

                        Text {
                            text: qsTr("Nền tảng")
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
                            Accessible.name: qsTr("Nền tảng")
                            onActivated: function(index) {
                                root.selectedPlatform = String(platformSelector.model[index].value)
                                contentFilter.currentIndex = 0
                                channelUrl.forceActiveFocus()
                            }
                        }
                    }

                    AppTextField {
                        id: channelUrl
                        Layout.fillWidth: true
                        placeholderText: root.placeholder()
                        selectByMouse: true
                        enabled: !root.channelActive
                        accessibleName: qsTr("Liên kết kênh")
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width >= 900 ? 4 : width >= 680 ? 3 : 2
                        columnSpacing: Theme.space12
                        rowSpacing: Theme.space12

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space4
                            Text { text: qsTr("Sắp xếp"); color: Theme.textMuted; font.pixelSize: Theme.label }
                            AppComboBox {
                                id: ranking
                                Layout.fillWidth: true
                                model: [{ "label": qsTr("Mới nhất"), "value": "newest" }, { "label": qsTr("Nhiều lượt xem"), "value": "popular" }]
                                textRole: "label"
                                valueRole: "value"
                                enabled: !root.channelActive
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space4
                            Text { text: qsTr("Số lượng tải"); color: Theme.textMuted; font.pixelSize: Theme.label }
                            AppSpinBox { id: channelLimit; Layout.fillWidth: true; from: 1; to: 100; value: 20; enabled: !root.channelActive }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space4
                            Text { text: qsTr("Loại nội dung"); color: Theme.textMuted; font.pixelSize: Theme.label }
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
                            Text { text: qsTr("Phạm vi quét"); color: Theme.textMuted; font.pixelSize: Theme.label }
                            AppComboBox {
                                id: scanScope
                                Layout.fillWidth: true
                                model: [
                                    { "label": qsTr("100 video"), "value": 100 },
                                    { "label": qsTr("300 video"), "value": 300 },
                                    { "label": qsTr("1000 video"), "value": 1000 },
                                    { "label": qsTr("Toàn bộ"), "value": 0 }
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
                            text: root.downloader.channelOutputDirectory.length > 0 ? root.downloader.channelOutputDirectory : qsTr("Chưa chọn thư mục")
                            color: root.downloader.channelOutputDirectory.length > 0 ? Theme.text : Theme.textMuted
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                        }
                        AppButton {
                            visible: !root.downloader.outputManaged
                            text: qsTr("Chọn thư mục")
                            compact: true
                            enabled: !root.channelActive
                            onClicked: root.downloader.chooseChannelOutputDirectory()
                        }
                        AppButton {
                            text: root.hasResults ? qsTr("Quét lại") : qsTr("Xem trước")
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
                        AppButton { visible: root.channelActive; text: qsTr("Hủy tải"); compact: true; tone: "danger"; onClicked: root.downloader.cancel() }
                    }
                    AppProgressBar { Layout.fillWidth: true; visible: root.channelActive; value: root.downloader.channelProgress }
                }

                AppSurface {
                    Layout.fillWidth: true
                    visible: root.hasResults
                    padding: Theme.space16

                    SectionHeader {
                        Layout.fillWidth: true
                        title: root.downloader.channelName.length > 0 ? root.downloader.channelName : qsTr("Video trong kênh")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        AppCheckBox {
                            text: qsTr("Chọn tất cả")
                            checked: root.downloader.channelSelectedCount > 0 && root.downloader.channelSelectedCount === root.downloader.channelSelectableCount
                            enabled: !root.channelActive
                            onToggled: root.downloader.selectAllChannel(checked)
                        }
                        Item { Layout.fillWidth: true }
                        AppButton {
                            text: qsTr("%1 (%2)").arg(qsTr("Tải video đã chọn")).arg(root.downloader.channelSelectedCount)
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

            }
        }
    }
}
