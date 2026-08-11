pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ApplicationWindow {
    id: root

    width: 1440
    height: 900
    minimumWidth: 1120
    minimumHeight: 720
    visible: false
    flags: Qt.Window
    title: ""
    color: Theme.window
    topPadding: 0
    leftPadding: 0
    rightPadding: 0
    bottomPadding: 0

    readonly property string routeSingleProjects: "single-projects"
    readonly property string routeSingleWorkspace: "single-workspace"
    readonly property string routeBatchProjects: "batch-projects"
    readonly property string routeBatchWorkspace: "batch-workspace"
    readonly property string routeBatchVideo: "batch-video"
    readonly property string routeDownloadProjects: "download-projects"
    readonly property string routeDownloadWorkspace: "download-workspace"
    readonly property string routePublishProjects: "publish-projects"
    readonly property string routePublishWorkspace: "publish-workspace"
    property string currentRoute: routeSingleProjects
    property string workspaceReturnRoute: routeSingleProjects
    property var routeHistory: [routeSingleProjects]
    property int routeHistoryIndex: 0
    readonly property bool compactNavigation: width < 1280
    readonly property bool modelStatusFailed: AppController.runtimeState === "failed"
    readonly property bool modelStatusBusy: AppController.runtimeState === "warming"
    readonly property bool routeCanGoBack: routeHistoryIndex > 0
    readonly property bool routeCanGoForward: routeHistoryIndex < routeHistory.length - 1
    // Loader.item is a QObject to qmllint, but its source component is DownloadsPage.
    // qmllint disable missing-property
    readonly property bool downloadCanGoBack: currentRoute === routeDownloadWorkspace
        && downloadWorkspaceLoader.status === Loader.Ready
        && downloadWorkspaceLoader.item !== null
        && downloadWorkspaceLoader.item.canGoBack
    readonly property bool downloadCanGoForward: currentRoute === routeDownloadWorkspace
        && downloadWorkspaceLoader.status === Loader.Ready
        && downloadWorkspaceLoader.item !== null
        && downloadWorkspaceLoader.item.canGoForward
    // qmllint enable missing-property
    readonly property bool canNavigateBack: downloadCanGoBack || routeCanGoBack
    readonly property bool canNavigateForward: downloadCanGoForward || routeCanGoForward

    // Reconcile in the background whenever the user returns from a browser.
    // This catches dashboard disconnects immediately without disabling the UI.
    onActiveChanged: {
        if (active && currentRoute === routePublishWorkspace
                && !AppController.tiktokPublishBusy)
            AppController.reconcileZernioConnections()
    }

    function routeIndex(route) {
        switch (route) {
        case routeSingleWorkspace:
            return 1
        case routeBatchProjects:
            return 2
        case routeBatchWorkspace:
            return 3
        case routeBatchVideo:
            return 4
        case routeDownloadProjects:
            return 5
        case routeDownloadWorkspace:
            return 6
        case routePublishProjects:
            return 7
        case routePublishWorkspace:
            return 8
        default:
            return 0
        }
    }

    function routeIsAvailable(route) {
        if (route === routeSingleProjects || route === routeBatchProjects
                || route === routeDownloadProjects || route === routePublishProjects)
            return true
        if (!AppController.hasOpenProject)
            return false
        if (route === routeSingleWorkspace)
            return AppController.projectType === "single"
        if (route === routeBatchWorkspace)
            return AppController.projectType === "batch"
        if (route === routeBatchVideo)
            return AppController.projectType === "batch" && AppController.isSelectedBatchVideo
        if (route === routeDownloadWorkspace)
            return AppController.projectType === "download"
        if (route === routePublishWorkspace)
            return AppController.projectType === "publish"
        return false
    }

    function resetRouteHistory(route) {
        routeHistory = [route]
        routeHistoryIndex = 0
        currentRoute = route
    }

    function pruneRouteHistory() {
        let filtered = []
        let nextIndex = 0
        for (let index = 0; index < routeHistory.length; ++index) {
            const route = routeHistory[index]
            if (!routeIsAvailable(route))
                continue
            if (index <= routeHistoryIndex)
                nextIndex = filtered.length
            filtered.push(route)
        }
        if (filtered.length === 0) {
            resetRouteHistory(workspaceReturnRoute)
            return
        }
        routeHistory = filtered
        routeHistoryIndex = Math.max(0, Math.min(nextIndex, filtered.length - 1))
        if (!routeIsAvailable(currentRoute))
            currentRoute = filtered[routeHistoryIndex]
    }

    function openProjectWorkspace(projectsRoute, workspaceRoute) {
        workspaceReturnRoute = projectsRoute
        resetRouteHistory(projectsRoute)
        navigate(workspaceRoute)
    }

    function replaceCurrentRoute(route) {
        if (route === currentRoute)
            return
        saveCurrentVideoSettings()
        let nextHistory = routeHistory.slice()
        nextHistory[routeHistoryIndex] = route
        if (routeHistoryIndex > 0 && nextHistory[routeHistoryIndex - 1] === route) {
            nextHistory = nextHistory.slice(0, routeHistoryIndex)
            routeHistoryIndex = nextHistory.length - 1
        }
        routeHistory = nextHistory
        currentRoute = route
    }

    function navigate(route) {
        if (route === currentRoute)
            return
        if (!routeIsAvailable(route)) {
            pruneRouteHistory()
            return
        }

        saveCurrentVideoSettings()
        let nextHistory = routeHistory.slice(0, routeHistoryIndex + 1)
        nextHistory.push(route)
        routeHistory = nextHistory
        routeHistoryIndex = nextHistory.length - 1
        currentRoute = route
    }

    function navigateBack() {
        if (downloadCanGoBack) {
            // qmllint disable missing-property
            downloadWorkspaceLoader.item.navigateBack()
            // qmllint enable missing-property
            return
        }
        pruneRouteHistory()
        if (!routeCanGoBack)
            return

        saveCurrentVideoSettings()
        routeHistoryIndex -= 1
        currentRoute = routeHistory[routeHistoryIndex]
    }

    function navigateForward() {
        if (downloadCanGoForward) {
            // qmllint disable missing-property
            downloadWorkspaceLoader.item.navigateForward()
            // qmllint enable missing-property
            return
        }
        pruneRouteHistory()
        if (!routeCanGoForward)
            return

        saveCurrentVideoSettings()
        routeHistoryIndex += 1
        currentRoute = routeHistory[routeHistoryIndex]
    }

    function saveCurrentVideoSettings() {
        if (currentRoute === routeBatchVideo
                && AppController.isSelectedBatchVideo
                && !AppController.isSelectedVideoProcessing)
            AppController.persistSelectedBatchVideoSettings()
    }

    Component.onCompleted: {
        I18n.language = AppController.settingsLanguage
    }

    Shortcut {
        sequence: "Ctrl+,"
        onActivated: settingsDialog.open()
    }

    Shortcut {
        sequence: "Alt+Left"
        enabled: root.canNavigateBack
        onActivated: root.navigateBack()
    }

    Shortcut {
        sequence: "Alt+Right"
        enabled: root.canNavigateForward
        onActivated: root.navigateForward()
    }

    ProjectSetupDialog {
        id: projectSetupDialog
    }

    UrlImportDialog {
        id: urlImportDialog
    }

    AboutDialog {
        id: aboutDialog
    }

    SettingsDialog {
        id: settingsDialog
    }

    BatchSettingsDialog {
        id: batchSettingsDialog
    }

    TranslationReviewDialog {
        id: translationReviewDialog
    }

    Connections {
        target: AppController

        function onVideoDeleted() {
            if (!AppController.hasOpenProject) {
                root.resetRouteHistory(root.workspaceReturnRoute)
                return
            }
            root.replaceCurrentRoute(root.workspaceReturnRoute)
            root.pruneRouteHistory()
        }

        function onBatchDeleted() {
            root.workspaceReturnRoute = root.routeBatchProjects
            root.resetRouteHistory(root.routeBatchProjects)
        }

        function onProjectSetupChanged() {
            root.pruneRouteHistory()
        }

        function onSelectedVideoChanged() {
            root.pruneRouteHistory()
        }

        function onSettingsChanged() {
            I18n.language = AppController.settingsLanguage
        }

        function onProjectPrepared() {
            if (AppController.projectType === "batch") {
                root.openProjectWorkspace(root.routeBatchProjects, root.routeBatchWorkspace)
            } else {
                if (AppController.projectType === "download") {
                    root.openProjectWorkspace(root.routeDownloadProjects, root.routeDownloadWorkspace)
                } else if (AppController.projectType === "publish") {
                    root.openProjectWorkspace(root.routePublishProjects, root.routePublishWorkspace)
                } else {
                    root.openProjectWorkspace(root.routeSingleProjects, root.routeSingleWorkspace)
                }
            }
        }
    }

    Overlay.modal: Rectangle {
        color: Theme.scrim
        Behavior on opacity {
            NumberAnimation {
                duration: Theme.motionStandard
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        AppMenuBar {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            canGoBack: root.canNavigateBack
            canGoForward: root.canNavigateForward
            onBackRequested: root.navigateBack()
            onForwardRequested: root.navigateForward()
            onNewSingleProjectRequested: {
                root.workspaceReturnRoute = root.routeSingleProjects
                projectSetupDialog.openForType("single")
            }
            onNewBatchProjectRequested: {
                root.workspaceReturnRoute = root.routeBatchProjects
                projectSetupDialog.openForType("batch")
            }
            onNewDownloadProjectRequested: {
                root.workspaceReturnRoute = root.routeDownloadProjects
                projectSetupDialog.openForType("download")
            }
            onNewPublishProjectRequested: {
                root.workspaceReturnRoute = root.routePublishProjects
                projectSetupDialog.openForType("publish")
            }
            onSettingsRequested: settingsDialog.open()
            onAboutRequested: aboutDialog.open()
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

        Rectangle {
            id: navigation

            Layout.preferredWidth: root.compactNavigation ? Theme.navigationCompact : Theme.navigationExpanded
            Layout.fillHeight: true
            color: Theme.sidebar

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                anchors.topMargin: 16
                anchors.bottomMargin: 14
                spacing: 8

                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48

                    RowLayout {
                        anchors.fill: parent
                        spacing: 11

                        BrandMark {
                            Layout.preferredWidth: 30
                            Layout.preferredHeight: 30
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: !root.compactNavigation
                            text: I18n.t("HaizFlow")
                            color: Theme.textOnDark
                            font.pixelSize: Theme.bodyLarge
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                        }

                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    Layout.bottomMargin: 12
                    color: Theme.divider
                }

                Text {
                    visible: !root.compactNavigation
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.bottomMargin: 2
                    text: I18n.t("WORKSPACE")
                    color: Theme.textSubtle
                    font.pixelSize: Theme.label
                    font.weight: Font.DemiBold
                    font.capitalization: Font.AllUppercase
                    textFormat: Text.PlainText
                }

                SidebarButton {
                    Layout.fillWidth: true
                    compact: root.compactNavigation
                    iconGlyph: "\uE896"
                    text: I18n.t("Downloads")
                    selected: root.currentRoute === root.routeDownloadProjects
                        || root.currentRoute === root.routeDownloadWorkspace
                    onClicked: {
                        AppController.refreshVideos()
                        root.navigate(root.routeDownloadProjects)
                    }
                }

                SidebarButton {
                    Layout.fillWidth: true
                    compact: root.compactNavigation
                    iconGlyph: "\uE714" // Used only by the compact navigation fallback.
                    text: I18n.t("Single")
                    selected: root.currentRoute === root.routeSingleProjects || root.currentRoute === root.routeSingleWorkspace
                    onClicked: {
                        AppController.refreshVideos()
                        root.navigate(root.routeSingleProjects)
                    }
                }


                SidebarButton {
                    Layout.fillWidth: true
                    compact: root.compactNavigation
                    iconGlyph: "\uE8FD" // Used only by the compact navigation fallback.
                    text: I18n.t("Batch")
                    selected: root.currentRoute === root.routeBatchProjects || root.currentRoute === root.routeBatchWorkspace || root.currentRoute === root.routeBatchVideo
                    onClicked: {
                        AppController.refreshVideos()
                        root.navigate(root.routeBatchProjects)
                    }
                }

                SidebarButton {
                    Layout.fillWidth: true
                    compact: root.compactNavigation
                    iconGlyph: "\uE789"
                    text: I18n.t("Social publishing")
                    selected: root.currentRoute === root.routePublishProjects
                        || root.currentRoute === root.routePublishWorkspace
                    onClicked: {
                        AppController.refreshVideos()
                        root.navigate(root.routePublishProjects)
                    }
                }

                Item {
                    Layout.fillHeight: true
                }

                RowLayout {
                    visible: !root.compactNavigation && (root.modelStatusBusy || root.modelStatusFailed)
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.rightMargin: 8
                    Layout.bottomMargin: 8
                    spacing: 9

                    Rectangle {
                        id: modelStatusIndicator
                        Layout.preferredWidth: 7
                        Layout.preferredHeight: 7
                        radius: 4
                        color: root.modelStatusFailed ? Theme.danger : root.modelStatusBusy ? Theme.warning : Theme.success

                        SequentialAnimation on opacity {
                            running: modelStatusIndicator.visible && root.modelStatusBusy && Theme.motionEnabled
                            loops: Animation.Infinite
                            NumberAnimation {
                                to: 0.35
                                duration: 750
                                easing.type: Easing.InOutSine
                            }
                            NumberAnimation {
                                to: 1
                                duration: 750
                                easing.type: Easing.InOutSine
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.runtimeStatus(AppController.statusMessage)
                        color: Theme.textOnDarkMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    Layout.bottomMargin: 4
                    color: Theme.divider
                }

                SidebarAboutLink {
                    Layout.fillWidth: true
                    compact: root.compactNavigation
                    onClicked: aboutDialog.open()
                }
            }

            Rectangle {
                anchors.right: parent.right
                height: parent.height
                width: 1
                color: Theme.divider
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: root.routeIndex(root.currentRoute)

                ProjectsPage {
                    projectType: "single"
                    // Python's generated qmltypes omit the constant flag; this model is stable.
                    // qmllint disable stale-property-read
                    projectModel: AppController.singleProjectModel
                    // qmllint enable stale-property-read
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: 24
                    Layout.bottomMargin: 24
                    onRequestNewProject: {
                        root.workspaceReturnRoute = root.routeSingleProjects
                        projectSetupDialog.openForType("single")
                    }
                    onOpenProject: {
                        root.openProjectWorkspace(root.routeSingleProjects, root.routeSingleWorkspace)
                    }
                }

                Loader {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: 24
                    Layout.bottomMargin: 24
                    active: root.currentRoute === root.routeSingleWorkspace
                    asynchronous: true
                    sourceComponent: Component {
                        CreateVideoPage {
                            onRequestReviewTranslation: translationReviewDialog.open()
                            onRequestUrlImport: urlImportDialog.openForMode("single")
                        }
                    }
                }

                ProjectsPage {
                    projectType: "batch"
                    // Python's generated qmltypes omit the constant flag; this model is stable.
                    // qmllint disable stale-property-read
                    projectModel: AppController.batchProjectModel
                    // qmllint enable stale-property-read
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: 24
                    Layout.bottomMargin: 24
                    onRequestNewProject: {
                        root.workspaceReturnRoute = root.routeBatchProjects
                        projectSetupDialog.openForType("batch")
                    }
                    onOpenProject: {
                        root.openProjectWorkspace(root.routeBatchProjects, root.routeBatchWorkspace)
                    }
                }

                Loader {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: 24
                    Layout.bottomMargin: 24
                    active: root.currentRoute === root.routeBatchWorkspace
                    asynchronous: true
                    sourceComponent: Component {
                        BatchPage {
                            onRequestBatchSettings: batchSettingsDialog.open()
                            onRequestUrlImport: urlImportDialog.openForMode("batch")
                            onOpenVideoDetail: {
                                root.workspaceReturnRoute = root.routeBatchWorkspace
                                root.navigate(root.routeBatchVideo)
                            }
                        }
                    }
                }

                Loader {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: 24
                    Layout.bottomMargin: 24
                    active: root.currentRoute === root.routeBatchVideo
                    asynchronous: true
                    sourceComponent: Component {
                        CreateVideoPage {
                            onRequestReviewTranslation: translationReviewDialog.open()
                            onRequestUrlImport: urlImportDialog.openForMode("batch")
                        }
                    }
                }

                ProjectsPage {
                    projectType: "download"
                    // Python's generated qmltypes omit the constant flag; this model is stable.
                    // qmllint disable stale-property-read
                    projectModel: AppController.downloadProjectModel
                    // qmllint enable stale-property-read
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: 24
                    Layout.bottomMargin: 24
                    onRequestNewProject: {
                        root.workspaceReturnRoute = root.routeDownloadProjects
                        projectSetupDialog.openForType("download")
                    }
                    onOpenProject: {
                        root.openProjectWorkspace(root.routeDownloadProjects, root.routeDownloadWorkspace)
                    }
                }

                Loader {
                    id: downloadWorkspaceLoader
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: 24
                    Layout.bottomMargin: 24
                    active: root.currentRoute === root.routeDownloadWorkspace
                    asynchronous: true
                    sourceComponent: Component {
                        DownloadsPage {
                            projectName: AppController.projectName
                            projectRoot: AppController.downloadOutputRoot
                        }
                    }
                }

                ProjectsPage {
                    projectType: "publish"
                    // qmllint disable stale-property-read
                    projectModel: AppController.publishProjectModel
                    // qmllint enable stale-property-read
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: 24
                    Layout.bottomMargin: 24
                    onRequestNewProject: {
                        root.workspaceReturnRoute = root.routePublishProjects
                        projectSetupDialog.openForType("publish")
                    }
                    onOpenProject: root.openProjectWorkspace(root.routePublishProjects, root.routePublishWorkspace)
                }

                Loader {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: 24
                    Layout.bottomMargin: 24
                    active: root.currentRoute === root.routePublishWorkspace
                    asynchronous: true
                    sourceComponent: Component {
                        SocialPublishPage {}
                    }
                }

            }
        }
        }
    }

    ModelSetupOverlay {
        anchors.fill: parent
    }
}
