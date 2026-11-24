pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

FocusScroll {
    id: root
    default property alias body: content.data
    property int maximumBodyHeight: 560
    property int spacing: Theme.space8
    Layout.fillWidth: true
    Layout.minimumHeight: 0
    Layout.preferredHeight: Math.min(contentHeight, maximumBodyHeight)
    contentWidth: width
    contentHeight: content.implicitHeight
    interactive: contentHeight > height
    property ColumnLayout contentLayout: ColumnLayout {
        id: content
        parent: root.contentItem
        width: root.width - (root.interactive ? Theme.space12 : 0)
        spacing: root.spacing
    }
}
