import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    property string subtitle: ""
    property int preferredWidth: 520
    property int preferredHeight: 0
    property int maximumWidth: 760
    property int maximumHeight: 720
    readonly property bool hasFooterActions: actionArea.children.length > 0
    readonly property int headerHeight: 60
    readonly property int footerHeight: hasFooterActions ? 56 : 0
    default property alias body: bodyColumn.data
    property alias footerActions: actionArea.data

    modal: true
    focus: true
    padding: 0
    width: Math.min(maximumWidth, preferredWidth, parent ? parent.width - 48 : preferredWidth)
    // Layout margins and a RowLayout's minimumHeight are not part of the
    // children's implicitHeight.  Count the complete chrome explicitly so
    // the footer can never overflow below the dialog background.
    implicitHeight: Math.min(maximumHeight, parent ? parent.height - 48 : maximumHeight,
        headerHeight + bodyColumn.implicitHeight + Theme.space32
            + (hasFooterActions ? footerHeight + 2 : 1))
    height: preferredHeight > 0
        ? Math.min(maximumHeight, preferredHeight, parent ? parent.height - 48 : preferredHeight)
        : implicitHeight
    closePolicy: Popup.CloseOnEscape
    parent: Overlay.overlay
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: parent ? Math.round((parent.height - height) / 2) : 0
    header: null
    footer: null

    background: Rectangle {
        objectName: "appDialogBackground"
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        objectName: "appDialogContent"
        spacing: 0

        RowLayout {
            id: dialogHeader
            Layout.fillWidth: true
            Layout.minimumHeight: root.headerHeight
            Layout.preferredHeight: root.headerHeight
            Layout.maximumHeight: root.headerHeight
            Layout.leftMargin: Theme.space20
            Layout.rightMargin: Theme.space12
            spacing: Theme.space12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    text: root.title
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.section
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    visible: root.subtitle.length > 0
                    text: root.subtitle
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
            }
            IconButton {
                glyph: IconCatalog.glyph("close")
                toolTipText: qsTr("Đóng")
                onClicked: root.close()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        ColumnLayout {
            id: bodyColumn
            objectName: "appDialogBody"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            Layout.leftMargin: Theme.space20
            Layout.rightMargin: Theme.space20
            Layout.topMargin: Theme.space16
            Layout.bottomMargin: Theme.space16
            spacing: Theme.space12
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: root.hasFooterActions ? 1 : 0
            visible: root.hasFooterActions
            color: Theme.divider
        }

        RowLayout {
            id: dialogFooter
            objectName: "appDialogFooter"
            Layout.fillWidth: true
            Layout.minimumHeight: root.footerHeight
            Layout.preferredHeight: root.footerHeight
            Layout.maximumHeight: root.footerHeight
            visible: root.hasFooterActions
            Layout.leftMargin: Theme.space20
            Layout.rightMargin: Theme.space20
            spacing: Theme.space8
            Item { Layout.fillWidth: true }
            RowLayout { id: actionArea; spacing: Theme.space8 }
        }
    }

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Motion.standard }
            NumberAnimation { property: "scale"; from: 0.985; to: 1; duration: Motion.standard; easing.type: Motion.enterEasing }
        }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Motion.fast }
    }
}
