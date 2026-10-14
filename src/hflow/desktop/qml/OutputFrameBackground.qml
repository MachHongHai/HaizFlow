pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Effects

Item {
    id: root
    required property Item sourceItem
    required property rect sourceRect
    property var videoSink: null
    readonly property real sourceRatio: sourceRect.width / Math.max(1, sourceRect.height)
    readonly property real smallWidth: Math.min(960, 540 * sourceRatio)
    readonly property real smallHeight: smallWidth / Math.max(0.001, sourceRatio)
    // Keep the previous apparent blur radius after increasing capture detail.
    readonly property int blurRadius: Math.min(64, Math.max(16,
        Math.round(16 * smallWidth / Math.max(1, Math.min(270, 480 * sourceRatio)))))
    readonly property bool blurReady: blurEffectLoader.status === Loader.Ready

    function requestRefresh() {
        if (visible && !refreshTimer.running)
            refreshTimer.start();
    }
    onVisibleChanged: {
        if (visible) requestRefresh();
        else refreshTimer.stop();
    }

    Timer {
        id: refreshTimer
        interval: 33
        onTriggered: capture.scheduleUpdate()
    }
    Connections {
        target: root.videoSink
        enabled: root.visible
        function onVideoFrameChanged() { root.requestRefresh(); }
    }
    ShaderEffectSource {
        id: capture
        objectName: "outputBackgroundCapture"
        sourceItem: root.sourceItem
        sourceRect: root.sourceRect
        textureSize: Qt.size(Math.ceil(root.smallWidth), Math.ceil(root.smallHeight))
        width: root.smallWidth
        height: root.smallHeight
        // Show the same bounded frame while the blur shaders incubate. This
        // avoids an empty portrait canvas without another media decoder.
        visible: !root.blurReady
        anchors.centerIn: parent
        scale: root.blurReady ? 1 : Math.max(root.width / width, root.height / height)
        smooth: true
        live: false
        Component.onCompleted: root.requestRefresh()
        onSourceRectChanged: root.requestRefresh()
        onTextureSizeChanged: root.requestRefresh()
        onSourceItemChanged: root.requestRefresh()
    }
    // Qt 6.11's MultiEffect synchronously creates this internal component
    // without checking for Loading/null. Complete its asynchronous load
    // first, in this same engine, before entering that native code path.
    Loader {
        id: blurPrerequisite
        objectName: "outputBlurPrerequisite"
        active: root.visible
        asynchronous: true
        source: "qrc:/data/BlurItem.qml"
        visible: false
        width: 0
        height: 0
    }
    Loader {
        id: blurEffectLoader
        objectName: "outputBlurEffectLoader"
        active: root.visible && blurPrerequisite.status === Loader.Ready
        asynchronous: true
        width: root.smallWidth
        height: root.smallHeight
        anchors.centerIn: parent
        scale: Math.max(root.width / width, root.height / height)
        onLoaded: root.requestRefresh()
        sourceComponent: Component {
            MultiEffect {
                objectName: "outputBackgroundBlur"
                anchors.fill: parent
                source: capture
                blurEnabled: true
                blur: 1
                blurMax: root.blurRadius
                autoPaddingEnabled: false
            }
        }
    }
}
