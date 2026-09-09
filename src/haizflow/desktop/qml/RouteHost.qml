pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

StackLayout {
    id: root

    required property string currentRoute
    // Loader.item is a QObject to qmllint; the guarded source is DownloadsPage.
    // qmllint disable missing-property
    readonly property bool downloadCanGoBack: currentRoute === "download-workspace" && downloadWorkspaceLoader.status === Loader.Ready && downloadWorkspaceLoader.item !== null && downloadWorkspaceLoader.item.canGoBack
    readonly property bool downloadCanGoForward: currentRoute === "download-workspace" && downloadWorkspaceLoader.status === Loader.Ready && downloadWorkspaceLoader.item !== null && downloadWorkspaceLoader.item.canGoForward
    // qmllint enable missing-property

    signal newProjectRequested(string projectType, string returnRoute)
    signal workspaceRequested(string returnRoute, string workspaceRoute)
    signal navigateRequested(string route)
    signal reviewTranslationRequested
    signal urlImportRequested(string mode)
    signal downloadProjectImportRequested(string mode)
    signal batchSettingsRequested

    function routeIndex(route) {
        const routes = {
            "single-projects": 0,
            "single-workspace": 1,
            "manual-projects": 2,
            "manual-workspace": 3,
            "batch-projects": 4,
            "batch-workspace": 5,
            "batch-video": 6,
            "download-projects": 7,
            "download-workspace": 8,
            "publish-projects": 9,
            "publish-workspace": 10,
            "home": 11,
            "projects": 12,
            "settings": 13
        };
        return routes[route] === undefined ? 0 : routes[route];
    }

    function workspaceRouteForType(projectType) {
        if (projectType === "manual")
            return "manual-workspace";
        if (projectType === "batch")
            return "batch-workspace";
        if (projectType === "download")
            return "download-workspace";
        if (projectType === "publish")
            return "publish-workspace";
        return "single-workspace";
    }

    function navigateDownloadBack() {
        // qmllint disable missing-property
        if (downloadWorkspaceLoader.status === Loader.Ready && downloadWorkspaceLoader.item)
            downloadWorkspaceLoader.item.navigateBack();
        // qmllint enable missing-property
    }

    function navigateDownloadForward() {
        // qmllint disable missing-property
        if (downloadWorkspaceLoader.status === Loader.Ready && downloadWorkspaceLoader.item)
            downloadWorkspaceLoader.item.navigateForward();
        // qmllint enable missing-property
    }

    currentIndex: routeIndex(currentRoute)

    ProjectsPage {
        projectType: "single"
        // qmllint disable stale-property-read
        projectModel: AppController.singleProjectModel
        // qmllint enable stale-property-read
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
        onRequestNewProject: root.newProjectRequested("single", "single-projects")
        onOpenProject: root.workspaceRequested("single-projects", "single-workspace")
    }

    Loader {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
        active: root.currentRoute === "single-workspace"
        asynchronous: true
        sourceComponent: Component {
            CreateVideoPage {
                onRequestReviewTranslation: root.reviewTranslationRequested()
                onRequestUrlImport: root.urlImportRequested("single")
                onRequestDownloadProjectImport: root.downloadProjectImportRequested("single")
            }
        }
    }

    ProjectsPage {
        projectType: "manual"
        // qmllint disable missing-property
        // The controller exposes a constant QObject model. The hand-written
        // tooling metadata cannot encode PySide's constant=True flag.
        // qmllint disable stale-property-read
        projectModel: AppController.manualProjectModel
        // qmllint enable stale-property-read
        // qmllint enable missing-property
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
        onRequestNewProject: root.newProjectRequested("manual", "manual-projects")
        onOpenProject: root.workspaceRequested("manual-projects", "manual-workspace")
    }

    Loader {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.leftMargin: UiMetrics.pageMargin
        Layout.rightMargin: UiMetrics.pageMargin
        Layout.topMargin: Theme.space16
        Layout.bottomMargin: Theme.space16
        active: root.currentRoute === "manual-workspace"
        asynchronous: true
        sourceComponent: Component {
            ManualWorkspace {
                onRequestUrlImport: root.urlImportRequested("manual")
                onRequestDownloadProjectImport: root.downloadProjectImportRequested("manual")
            }
        }
    }

    ProjectsPage {
        projectType: "batch"
        // qmllint disable stale-property-read
        projectModel: AppController.batchProjectModel
        // qmllint enable stale-property-read
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
        onRequestNewProject: root.newProjectRequested("batch", "batch-projects")
        onOpenProject: root.workspaceRequested("batch-projects", "batch-workspace")
    }

    Loader {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
        active: root.currentRoute === "batch-workspace"
        asynchronous: true
        sourceComponent: Component {
            BatchPage {
                onRequestBatchSettings: root.batchSettingsRequested()
                onRequestUrlImport: root.urlImportRequested("batch")
                onRequestDownloadProjectImport: root.downloadProjectImportRequested("batch")
                onOpenVideoDetail: root.workspaceRequested("batch-workspace", "batch-video")
            }
        }
    }

    Loader {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
        active: root.currentRoute === "batch-video"
        asynchronous: true
        sourceComponent: Component {
            CreateVideoPage {
                onRequestReviewTranslation: root.reviewTranslationRequested()
                onRequestUrlImport: root.urlImportRequested("batch")
                onRequestDownloadProjectImport: root.downloadProjectImportRequested("single")
            }
        }
    }

    ProjectsPage {
        projectType: "download"
        // qmllint disable stale-property-read
        projectModel: AppController.downloadProjectModel
        // qmllint enable stale-property-read
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
        onRequestNewProject: root.newProjectRequested("download", "download-projects")
        onOpenProject: root.workspaceRequested("download-projects", "download-workspace")
    }

    Loader {
        id: downloadWorkspaceLoader
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
        active: root.currentRoute === "download-workspace"
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
        Layout.margins: UiMetrics.pageMargin
        onRequestNewProject: root.newProjectRequested("publish", "publish-projects")
        onOpenProject: root.workspaceRequested("publish-projects", "publish-workspace")
    }

    Loader {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
        active: root.currentRoute === "publish-workspace"
        asynchronous: true
        sourceComponent: Component {
            SocialPublishPage {}
        }
    }

    HomePage {
        // qmllint disable stale-property-read
        projectModel: AppController.projectModel
        // qmllint enable stale-property-read
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.leftMargin: UiMetrics.pageMargin + Theme.space12
        Layout.rightMargin: UiMetrics.pageMargin + Theme.space12
        Layout.topMargin: UiMetrics.pageMargin
        Layout.bottomMargin: UiMetrics.pageMargin
        onNewProjectRequested: function (projectType) {
            root.newProjectRequested(projectType, "home");
        }
        onRecentProjectRequested: function (index, projectType) {
            if (AppController.selectProject(index))
                root.workspaceRequested("home", root.workspaceRouteForType(projectType));
        }
        onProjectsRequested: root.navigateRequested("projects")
        onDownloadsRequested: root.navigateRequested("download-projects")
        onPublishingRequested: root.navigateRequested("publish-projects")
    }

    ProjectsHubPage {
        // qmllint disable missing-property stale-property-read
        projectModel: AppController.projectBrowserModel
        // qmllint enable missing-property stale-property-read
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
        onRequestNewProject: function (projectType) {
            root.newProjectRequested(projectType, "projects");
        }
        onOpenProject: function (index, projectType) {
            // qmllint disable missing-property
            if (AppController.selectProjectFromBrowser(index))
                root.workspaceRequested("projects", root.workspaceRouteForType(projectType));
        // qmllint enable missing-property
        }
    }

    SettingsPage {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: UiMetrics.pageMargin
    }
}
