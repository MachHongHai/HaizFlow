import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root

    // qmllint disable stale-property-read
    readonly property var downloader: AppController.mediaDownloader
    // qmllint enable stale-property-read
    required property string projectName
    required property string projectRoot
    property int currentPage: 0
    readonly property bool canGoBack: false
    readonly property bool canGoForward: false

    function resetNavigation() { currentPage = 0 }
    function navigateBack() {}
    function navigateForward() {}
    onProjectRootChanged: resetNavigation()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UiMetrics.pageMargin
        spacing: Theme.space16

        PageHeader {
            Layout.fillWidth: true
            title: qsTr("Tải xuống")

            ProjectHeaderActions {
                projectFolderText: qsTr("Mở thư mục đầu ra")
                deleteEnabled: !root.downloader.currentProjectHasWork
                onProjectFolderRequested: AppController.openDownloadOutputFolder()
                onDeleteRequested: AppController.deleteCurrentProject()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.maximumWidth: 1120
            Layout.alignment: Qt.AlignHCenter
            spacing: Theme.space12

            AppTabBar {
                Layout.preferredWidth: Math.min(420, root.width * 0.5)
                currentIndex: root.currentPage
                tabs: [qsTr("Video"), qsTr("Kênh"), qsTr("Âm thanh")]
                onActivated: function(index) {
                    root.currentPage = index
                }
            }
            Item { Layout.fillWidth: true }
            StatusBadge {
                visible: root.downloader.currentProjectHasWork
                status: "processing"
                label: qsTr("Tác vụ nền đang chạy")
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.maximumWidth: 1120
            Layout.alignment: Qt.AlignHCenter
            currentIndex: root.currentPage

            VideoDownloadPage { downloader: root.downloader }
            ChannelDownloadPage { downloader: root.downloader }
            AudioDownloadPage { downloader: root.downloader }
        }

        DownloadQueueStatus {
            Layout.fillWidth: true
            Layout.maximumWidth: 1120
            Layout.alignment: Qt.AlignHCenter
            downloader: root.downloader
        }
    }
}
