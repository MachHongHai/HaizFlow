import QtQuick
import "."

Rectangle {
    id: root
    property url source: ""
    property string fallbackIcon: "video"
    readonly property real pixelRatio: Screen.devicePixelRatio
    property int decodeWidth: 64
    property int decodeHeight: 64
    function scheduleDecodeSize() {
        if (visible && !decodeTimer.running)
            decodeTimer.start();
    }
    onWidthChanged: scheduleDecodeSize()
    onHeightChanged: scheduleDecodeSize()
    onPixelRatioChanged: scheduleDecodeSize()
    onVisibleChanged: if (visible) scheduleDecodeSize()
    Component.onCompleted: scheduleDecodeSize()

    Timer {
        id: decodeTimer
        interval: 120
        onTriggered: {
            root.decodeWidth = Math.max(64, Math.ceil(root.width * root.pixelRatio / 64) * 64);
            root.decodeHeight = Math.max(64, Math.ceil(root.height * root.pixelRatio / 64) * 64);
        }
    }

    radius: Theme.radiusTiny
    color: Theme.video
    border.width: 1
    border.color: Theme.outline
    clip: true

    Image {
        id: thumbnailImage
        anchors.fill: parent
        source: root.source
        sourceSize.width: root.decodeWidth
        sourceSize.height: root.decodeHeight
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        visible: status === Image.Ready
    }

    FluentIcon {
        anchors.centerIn: parent
        visible: root.source.toString().length === 0 || thumbnailImage.status === Image.Error
        width: 20
        height: 20
        name: root.fallbackIcon
        iconColor: Theme.textDisabled
        iconSize: 19
    }
}
