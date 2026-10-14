pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root
    property string title: ""
    property string platform: ""
    property string uploader: ""
    property string duration: ""
    property string thumbnail: ""
    implicitHeight: 112
    radius: Theme.radiusSmall
    color: Theme.surfaceElevated
    border.width: 1
    border.color: Theme.outline

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.space12
        spacing: Theme.space12
        Rectangle {
            Layout.preferredWidth: 132
            Layout.preferredHeight: 76
            radius: Theme.radiusTiny
            color: Theme.surfaceStrong
            clip: true
            Image {
                id: thumbnailImage
                anchors.fill: parent
                source: root.thumbnail
                sourceSize.width: 264
                sourceSize.height: 152
                asynchronous: true
                fillMode: Image.PreserveAspectCrop
                visible: status === Image.Ready
            }
            ThumbnailFallback {
                anchors.fill: parent
                visible: root.thumbnail.length === 0 || thumbnailImage.status === Image.Error
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space4
            Text {
                Layout.fillWidth: true
                text: root.title
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true
                text: [root.platform, root.uploader, root.duration].filter(value => value.length > 0).join(" | ")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                elide: Text.ElideRight
                textFormat: Text.PlainText
            }
        }
    }
}
