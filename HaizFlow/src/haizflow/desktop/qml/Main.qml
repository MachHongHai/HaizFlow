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

    readonly property string routeHome: "home"
    readonly property string routeProjects: "projects"
    readonly property string routeSettings: "settings"
    readonly property string routeAbout: "about"
    readonly property string routeSingleProjects: "single-projects"
    readonly property string routeSingleWorkspace: "single-workspace"
    readonly property string routeManualProjects: "manual-projects"
    readonly property string routeManualWorkspace: "manual-workspace"
    readonly property string routeBatchProjects: "batch-projects"
    readonly property string routeBatchWorkspace: "batch-workspace"
    readonly property string routeBatchVideo: "batch-video"
    readonly property string routeDownloadProjects: "download-projects"
    readonly property string routeDownloadWorkspace: "download-workspace"
    readonly property string routePublishProjects: "publish-projects"
    readonly property string routePublishWorkspace: "publish-workspace"
    property string currentRoute: routeHome
    property string workspaceReturnRoute: routeHome
    property var routeHistory: [routeHome]
    property int routeHistoryIndex: 0
    readonly property bool compactNavigation: width < 1280
    readonly property bool modelStatusFailed: AppController.runtimeState === "failed"
    readonly property bool modelStatusBusy: AppController.runtimeState === "warming"
    readonly property bool routeCanGoBack: routeHistoryIndex > 0
    readonly property bool routeCanGoForward: routeHistoryIndex < routeHistory.length - 1
    readonly property bool projectWorkspaceVisible: currentRoute === routeSingleWorkspace || currentRoute === routeManualWorkspace || currentRoute === routeBatchWorkspace || currentRoute === routeBatchVideo || currentRoute === routeDownloadWorkspace || currentRoute === routePublishWorkspace
    readonly property bool globalNavigationBlocked: lazyDialogVisible(projectSetupDialogLoader) || lazyDialogVisible(urlImportDialogLoader) || lazyDialogVisible(downloadProjectSourceDialogLoader) || lazyDialogVisible(batchSettingsDialogLoader) || lazyDialogVisible(translationReviewDialogLoader) || appAlertDialog.visible || modelSetupOverlayLoader.active
    readonly property bool downloadCanGoBack: routeHost.downloadCanGoBack
    readonly property bool downloadCanGoForward: routeHost.downloadCanGoForward
    readonly property bool canNavigateBack: !globalNavigationBlocked && (downloadCanGoBack || routeCanGoBack)
    readonly property bool canNavigateForward: !globalNavigationBlocked && (downloadCanGoForward || routeCanGoForward)

    function navigationSection() {
        if (currentRoute === routeProjects)
            return "projects";
        if (currentRoute === routeSettings)
            return "settings";
        if (currentRoute === routeAbout)
            return "";
        if (currentRoute === routeDownloadProjects)
            return "downloads";
        if (currentRoute === routePublishProjects)
            return "social";
        return "home";
    }

    function lazyDialogVisible(loader) {
        return loader.status === Loader.Ready && loader.item !== null && loader.item.visible;
    }

    // Reconcile in the background whenever the user returns from a browser.
    // This catches dashboard disconnects immediately without disabling the UI.
    onActiveChanged: {
        if (active && currentRoute === routePublishWorkspace && !AppController.tiktokPublishBusy)
            AppController.reconcileZernioConnections();
    }

    function routeIsAvailable(route) {
        if (route === routeHome || route === routeProjects || route === routeSettings || route === routeAbout || route === routeSingleProjects || route === routeManualProjects || route === routeBatchProjects || route === routeDownloadProjects || route === routePublishProjects)
            return true;
        if (!AppController.hasOpenProject)
            return false;
        if (route === routeSingleWorkspace)
            return AppController.projectType === "single";
        if (route === routeManualWorkspace)
            return AppController.projectType === "manual";
        if (route === routeBatchWorkspace)
            return AppController.projectType === "batch";
        if (route === routeBatchVideo)
            return AppController.projectType === "batch" && AppController.isSelectedBatchVideo;
        if (route === routeDownloadWorkspace)
            return AppController.projectType === "download";
        if (route === routePublishWorkspace)
            return AppController.projectType === "publish";
        return false;
    }

    function resetRouteHistory(route) {
        routeHistory = [route];
        routeHistoryIndex = 0;
        currentRoute = route;
    }

    function pruneRouteHistory() {
        let filtered = [];
        let nextIndex = 0;
        for (let index = 0; index < routeHistory.length; ++index) {
            const route = routeHistory[index];
            if (!routeIsAvailable(route))
                continue;
            if (index <= routeHistoryIndex)
                nextIndex = filtered.length;
            filtered.push(route);
        }
        if (filtered.length === 0) {
            resetRouteHistory(workspaceReturnRoute);
            return;
        }
        routeHistory = filtered;
        routeHistoryIndex = Math.max(0, Math.min(nextIndex, filtered.length - 1));
        if (!routeIsAvailable(currentRoute))
            currentRoute = filtered[routeHistoryIndex];
    }

    function openProjectWorkspace(projectsRoute, workspaceRoute) {
        workspaceReturnRoute = projectsRoute;
        resetRouteHistory(projectsRoute);
        navigate(workspaceRoute);
    }

    function replaceCurrentRoute(route) {
        if (route === currentRoute)
            return;
        saveCurrentVideoSettings();
        let nextHistory = routeHistory.slice();
        nextHistory[routeHistoryIndex] = route;
        if (routeHistoryIndex > 0 && nextHistory[routeHistoryIndex - 1] === route) {
            nextHistory = nextHistory.slice(0, routeHistoryIndex);
            routeHistoryIndex = nextHistory.length - 1;
        }
        routeHistory = nextHistory;
        currentRoute = route;
    }

    function navigate(route) {
        if (route === currentRoute)
            return;
        if (!routeIsAvailable(route)) {
            pruneRouteHistory();
            return;
        }

        saveCurrentVideoSettings();
        let nextHistory = routeHistory.slice(0, routeHistoryIndex + 1);
        nextHistory.push(route);
        routeHistory = nextHistory;
        routeHistoryIndex = nextHistory.length - 1;
        currentRoute = route;
    }

    function navigateBack() {
        if (globalNavigationBlocked)
            return;
        if (downloadCanGoBack) {
            routeHost.navigateDownloadBack();
            return;
        }
        pruneRouteHistory();
        if (!routeCanGoBack)
            return;
        saveCurrentVideoSettings();
        routeHistoryIndex -= 1;
        currentRoute = routeHistory[routeHistoryIndex];
    }

    function navigateForward() {
        if (globalNavigationBlocked)
            return;
        if (downloadCanGoForward) {
            routeHost.navigateDownloadForward();
            return;
        }
        pruneRouteHistory();
        if (!routeCanGoForward)
            return;
        saveCurrentVideoSettings();
        routeHistoryIndex += 1;
        currentRoute = routeHistory[routeHistoryIndex];
    }

    function saveCurrentVideoSettings() {
        if (currentRoute === routeBatchVideo && AppController.isSelectedBatchVideo && !AppController.isSelectedVideoProcessing)
            AppController.persistSelectedBatchVideoSettings();
    }

    Component.onCompleted: {
        I18n.language = AppController.settingsLanguage;
        AppController.enableInAppAlerts();
    }

    Binding {
        target: UiMetrics
        property: "viewportWidth"
        value: root.width
    }

    Binding {
        target: UiMetrics
        property: "viewportHeight"
        value: root.height
    }

    LazyDialogLoader {
        id: projectSetupDialogLoader
        sourceComponent: Component {
            ProjectSetupDialog { onClosed: projectSetupDialogLoader.release() }
        }
    }

    LazyDialogLoader {
        id: urlImportDialogLoader
        sourceComponent: Component {
            UrlImportDialog { onClosed: urlImportDialogLoader.release() }
        }
    }

    LazyDialogLoader {
        id: downloadProjectSourceDialogLoader
        sourceComponent: Component {
            DownloadProjectSourceDialog { onClosed: downloadProjectSourceDialogLoader.release() }
        }
    }

    LazyDialogLoader {
        id: batchSettingsDialogLoader
        sourceComponent: Component {
            BatchSettingsDialog { onClosed: batchSettingsDialogLoader.release() }
        }
    }

    LazyDialogLoader {
        id: translationReviewDialogLoader
        sourceComponent: Component {
            TranslationReviewDialog { onClosed: translationReviewDialogLoader.release() }
        }
    }

    AppAlertDialog {
        id: appAlertDialog
    }

    ConfirmDialog {
        id: appConfirmationDialog
        property bool responseSent: false
        confirmText: qsTr("Xác nhận")
        onOpened: responseSent = false
        onConfirmed: {
            responseSent = true;
            AppController.respondToAppConfirmation(true);
        }
        onRejected: {
            if (!responseSent) {
                responseSent = true;
                AppController.respondToAppConfirmation(false);
            }
        }
    }

    Connections {
        target: AppController

        function onVideoDeleted() {
            if (!AppController.hasOpenProject) {
                root.resetRouteHistory(root.workspaceReturnRoute);
                return;
            }
            root.replaceCurrentRoute(root.workspaceReturnRoute);
            root.pruneRouteHistory();
        }

        function onBatchDeleted() {
            root.workspaceReturnRoute = root.routeBatchProjects;
            root.resetRouteHistory(root.routeBatchProjects);
        }

        function onProjectSetupChanged() {
            root.pruneRouteHistory();
        }

        function onSelectedVideoChanged() {
            root.pruneRouteHistory();
        }

        function onSettingsChanged() {
            I18n.language = AppController.settingsLanguage;
        }

        function onAppAlertRequested(title, message, severity) {
            if (severity === "critical")
                appAlertDialog.showAlert(title, message, severity);
            else
                toastStack.show(title, message, severity, severity === "warning" ? 6200 : 4200);
        }

        function onAppConfirmationRequested(title, message) {
            appConfirmationDialog.title = title;
            appConfirmationDialog.message = message;
            appConfirmationDialog.open();
        }

        function onProjectPrepared() {
            const returnRoute = root.workspaceReturnRoute === root.routeHome || root.workspaceReturnRoute === root.routeProjects ? root.workspaceReturnRoute : "";
            if (AppController.projectType === "batch") {
                root.openProjectWorkspace(returnRoute || root.routeBatchProjects, root.routeBatchWorkspace);
            } else if (AppController.projectType === "manual") {
                root.openProjectWorkspace(returnRoute || root.routeManualProjects, root.routeManualWorkspace);
            } else {
                if (AppController.projectType === "download") {
                    root.openProjectWorkspace(returnRoute || root.routeDownloadProjects, root.routeDownloadWorkspace);
                } else if (AppController.projectType === "publish") {
                    root.openProjectWorkspace(returnRoute || root.routePublishProjects, root.routePublishWorkspace);
                } else {
                    root.openProjectWorkspace(returnRoute || root.routeSingleProjects, root.routeSingleWorkspace);
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
            visible: !root.projectWorkspaceVisible
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 40 : 0
            canGoBack: root.canNavigateBack
            canGoForward: root.canNavigateForward
            onBackRequested: root.navigateBack()
            onForwardRequested: root.navigateForward()
            onHomeRequested: root.navigate(root.routeHome)
            onNewSingleProjectRequested: {
                root.workspaceReturnRoute = root.routeSingleProjects;
                projectSetupDialogLoader.invoke("openForType", ["single"]);
            }
            onManualProjectRequested: {
                root.workspaceReturnRoute = root.routeManualProjects;
                projectSetupDialogLoader.invoke("openForType", ["manual"]);
            }
            onNewBatchProjectRequested: {
                root.workspaceReturnRoute = root.routeBatchProjects;
                projectSetupDialogLoader.invoke("openForType", ["batch"]);
            }
            onNewDownloadProjectRequested: {
                root.workspaceReturnRoute = root.routeDownloadProjects;
                projectSetupDialogLoader.invoke("openForType", ["download"]);
            }
            onNewPublishProjectRequested: {
                root.workspaceReturnRoute = root.routePublishProjects;
                projectSetupDialogLoader.invoke("openForType", ["publish"]);
            }
            onSettingsRequested: root.navigate(root.routeSettings)
            onAboutRequested: root.navigate(root.routeAbout)
        }

        WorkspaceToolbar {
            visible: root.projectWorkspaceVisible
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? UiMetrics.toolbarHeight : 0
            title: AppController.projectName
            statusText: I18n.taskStateLabel(AppController.selectedStatus)
            canGoBack: root.canNavigateBack
            onBackRequested: root.navigateBack()
            onHomeRequested: root.navigate(root.routeHome)
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            NavigationRail {
                visible: !root.projectWorkspaceVisible
                Layout.preferredWidth: root.compactNavigation ? Theme.navigationCompact : Theme.navigationExpanded
                Layout.fillHeight: true
                compact: root.compactNavigation
                currentSection: root.navigationSection()
                runtimeState: AppController.runtimeState
                runtimeMessage: I18n.runtimeStatus(AppController.statusMessage)
                onSectionRequested: function (section) {
                    AppController.refreshVideos();
                    if (section === "projects")
                        root.navigate(root.routeProjects);
                    else if (section === "downloads")
                        root.navigate(root.routeDownloadProjects);
                    else if (section === "social")
                        root.navigate(root.routePublishProjects);
                    else
                        root.navigate(root.routeHome);
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                RouteHost {
                    id: routeHost
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentRoute: root.currentRoute

                    onNewProjectRequested: function (projectType, returnRoute) {
                        root.workspaceReturnRoute = returnRoute;
                        projectSetupDialogLoader.invoke("openForType", [projectType]);
                    }
                    onWorkspaceRequested: function (returnRoute, workspaceRoute) {
                        root.openProjectWorkspace(returnRoute, workspaceRoute);
                    }
                    onNavigateRequested: function (route) {
                        AppController.refreshVideos();
                        root.navigate(route);
                    }
                    onReviewTranslationRequested: translationReviewDialogLoader.invoke("open", [])
                    onUrlImportRequested: function (mode) {
                        urlImportDialogLoader.invoke("openForMode", [mode]);
                    }
                    onDownloadProjectImportRequested: function (mode) {
                        downloadProjectSourceDialogLoader.invoke("openForMode", [mode]);
                    }
                    onBatchSettingsRequested: batchSettingsDialogLoader.invoke("open", [])
                }
            }
        }

        ActivityTray {
            Layout.fillWidth: true
            showDetails: false
            activityState: root.modelStatusFailed ? "failed" : root.modelStatusBusy || AppController.isProcessing ? "processing" : "ready"
            message: root.modelStatusFailed || root.modelStatusBusy ? I18n.runtimeStatus(AppController.statusMessage) : AppController.isProcessing ? AppController.processingText : ""
            progress: AppController.isSelectedVideoProcessing ? Math.max(0, Math.min(1, AppController.selectedProgress / 100)) : -1
        }
    }

    Loader {
        id: modelSetupOverlayLoader
        anchors.fill: parent
        active: AppController.modelSetupVisible
        sourceComponent: Component {
            ModelSetupOverlay {}
        }
    }

    ToastStack {
        id: toastStack
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: Theme.space16 + (root.projectWorkspaceVisible ? UiMetrics.toolbarHeight : 40)
        anchors.rightMargin: Theme.space16
        width: Math.min(380, root.width - Theme.space32)
        z: 200
    }
}
