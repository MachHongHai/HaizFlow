import QtQuick
import "."

Rectangle {
    id: root
    property url source: ""
    property string fallbackIcon: "video"

    radius: Theme.radiusTiny
    color: Theme.video
    border.width: 1
    border.color: Theme.outline
    clip: true

    Image {
        id: thumbnailImage
        anchors.fill: parent
        source: root.source
        sourceSize.width: Math.max(1, Math.round(width * 2))
        sourceSize.height: Math.max(1, Math.round(height * 2))
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
