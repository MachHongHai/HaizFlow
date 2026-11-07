import QtQuick

Loader {
    id: root
    property bool selected: false
    property bool workspaceVisible: false
    property bool visited: false
    // Retain lightweight tab UI only within Settings; release it on leaving.
    active: workspaceVisible && (selected || visited)
    asynchronous: true
    onLoaded: visited = true
    onWorkspaceVisibleChanged: if (!workspaceVisible) visited = false
}
