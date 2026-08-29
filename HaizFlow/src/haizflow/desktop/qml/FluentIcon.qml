import QtQuick
import "."

Item {
    id: root
    property string name: ""
    property color iconColor: Theme.textMuted
    property int iconSize: Theme.icon
    readonly property bool accentVariant: iconColor === Theme.interactive || iconColor === Theme.focus
    readonly property url assetSource: IconCatalog.asset(name, accentVariant)

    Image {
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: root.assetSource
        sourceSize.width: root.iconSize * 2
        sourceSize.height: root.iconSize * 2
        fillMode: Image.PreserveAspectFit
        visible: root.assetSource.toString().length > 0
        asynchronous: true
        cache: true
    }

    AppIcon {
        anchors.fill: parent
        visible: root.assetSource.toString().length === 0
        glyph: IconCatalog.glyph(root.name)
        iconColor: root.iconColor
        iconSize: root.iconSize
    }
}
