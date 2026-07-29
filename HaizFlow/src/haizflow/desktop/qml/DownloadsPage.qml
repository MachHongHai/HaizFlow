import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root

    // Python's generated qmltypes omit the constant flag; this controller is stable.
    // qmllint disable stale-property-read
    readonly property var downloader: AppController.mediaDownloader
    // qmllint enable stale-property-read
    required property string projectName
    required property string projectRoot
    property int currentPage: 0
    property var pageHistory: [0]
    property int pageHistoryIndex: 0
    readonly property bool canGoBack: pageHistoryIndex > 0
    readonly property bool canGoForward: pageHistoryIndex < pageHistory.length - 1

    function navigateTo(page) {
        if (page === currentPage)
            return

        let nextHistory = pageHistory.slice(0, pageHistoryIndex + 1)
        nextHistory.push(page)
        pageHistory = nextHistory
        pageHistoryIndex = nextHistory.length - 1
        currentPage = page
    }

    function navigateBack() {
        if (!canGoBack)
            return

        pageHistoryIndex -= 1
        currentPage = pageHistory[pageHistoryIndex]
    }

    function navigateForward() {
        if (!canGoForward)
            return

        pageHistoryIndex += 1
        currentPage = pageHistory[pageHistoryIndex]
    }

    StackLayout {
        anchors.fill: parent
        anchors.margins: Theme.space20
        currentIndex: root.currentPage

        Item {
            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.space16

                PageHeader {
                    Layout.fillWidth: true
                    title: root.projectName
                    subtitle: root.projectRoot

                    ProjectHeaderActions {
                        projectFolderText: I18n.t("Open output folder")
                        deleteEnabled: !root.downloader.currentProjectHasWork
                        onProjectFolderRequested: AppController.openDownloadOutputFolder()
                        onDeleteRequested: AppController.deleteCurrentProject()
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Choose a download type")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: width >= 1000 ? 3 : width >= 640 ? 2 : 1
                    columnSpacing: Theme.space16
                    rowSpacing: Theme.space16

                    DownloadActionCard {
                        Layout.fillWidth: true
                        text: I18n.t("Channel")
                        subtitle: I18n.t("Browse public channel videos")
                        onClicked: root.navigateTo(1)
                    }
                    DownloadActionCard {
                        Layout.fillWidth: true
                        text: I18n.t("Video")
                        subtitle: I18n.t("Download one video from a link")
                        onClicked: root.navigateTo(2)
                    }
                    DownloadActionCard {
                        Layout.fillWidth: true
                        text: I18n.t("Audio")
                        subtitle: I18n.t("Download or extract audio")
                        onClicked: root.navigateTo(3)
                    }
                }

                DownloadQueueStatus {
                    Layout.fillWidth: true
                    downloader: root.downloader
                }

                Item { Layout.fillHeight: true }
            }
        }

        ChannelDownloadPage {
            downloader: root.downloader
        }

        VideoDownloadPage {
            downloader: root.downloader
        }

        AudioDownloadPage {
            downloader: root.downloader
        }
    }
}
