pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property string projectTitle: ""
    property bool hasVideo: false
    property bool hasOutput: false
    property bool exportEnabled: true
    property bool exportBusy: false
    property bool hasProject: false
    property bool canUndo: false
    property bool canRedo: false
    property bool hasSelection: false
    property bool sourceSelected: false
    property bool resultSelected: false
    property bool comparing: false
    property real previewZoomPercent: 100
    property string outputFormat: "keep_ratio"
    property real outputSpeed: 1.0
    signal outputSpeedEdited(real value)
    property bool outputFormatEditable: true
    readonly property bool compactTools: width < 1120
    readonly property int toolControlSize: width < 960 ? 32 : 40

    signal undoRequested()
    signal redoRequested()
    signal compareToggled()
    signal previewZoomInRequested()
    signal previewZoomOutRequested()
    signal seekRequested(real offset)
    signal resultSplitRequested()
    signal outputFormatEdited(string value)
    signal exportRequested()
    signal exportProgressRequested()
    signal projectFolderRequested()
    signal inputVideoRequested()
    signal videoFolderRequested()
    signal technicalLogRequested()
    signal projectDeleteRequested()
    signal resetWorkspaceRequested()

    implicitHeight: 42
    color: Theme.surface

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.divider
    }

    RowLayout {
        id: frameGroup
        anchors.left: parent.left
        anchors.leftMargin: Theme.space16
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, historyGroup.x - Theme.space16 * 2)
        spacing: Theme.space8
        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: 0
            visible: !root.hasVideo || frameGroup.width >= 80
            text: root.projectTitle
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            font.weight: Font.DemiBold
            elide: Text.ElideMiddle
            textFormat: Text.PlainText
            Accessible.name: root.projectTitle
        }
    }

    RowLayout {
        id: historyGroup
        objectName: "manualHistoryGroup"
        anchors.verticalCenter: parent.verticalCenter
        x: Math.max(Theme.space16, Math.min((root.width - width) / 2,
            outputGroup.x - width - Theme.space16))
        spacing: root.compactTools ? Theme.space4 : Theme.space8

        StudioIconButton {
            objectName: "manualUndoButton"
            visible: root.hasVideo
            controlSize: root.toolControlSize
            iconName: "undo"
            enabled: root.canUndo
            toolTipText: qsTr("Hoàn tác")
            onClicked: root.undoRequested()
        }
        StudioIconButton {
            objectName: "manualRedoButton"
            visible: root.hasVideo
            controlSize: root.toolControlSize
            iconName: "redo"
            enabled: root.canRedo
            toolTipText: qsTr("Làm lại")
            onClicked: root.redoRequested()
        }

        StudioButton {
            objectName: "manualCompareButton"
            visible: root.hasVideo
            text: qsTr("So sánh")
            iconName: "video"
            variant: root.comparing ? "secondary" : "ghost"
            checked: root.comparing
            checkable: true
            toolTipText: qsTr("Hiện hoặc ẩn video nguồn")
            onClicked: root.compareToggled()
        }
        StudioIconButton {
            objectName: "manualPreviewZoomOutButton"
            visible: root.hasVideo
            controlSize: root.toolControlSize
            iconName: "zoomOut"
            enabled: root.previewZoomPercent > 50
            toolTipText: qsTr("Thu nhỏ preview")
            onClicked: root.previewZoomOutRequested()
        }
        StudioIconButton {
            objectName: "manualPreviewZoomInButton"
            visible: root.hasVideo
            controlSize: root.toolControlSize
            iconName: "zoomIn"
            enabled: root.previewZoomPercent < 400
            toolTipText: qsTr("Phóng to preview")
            onClicked: root.previewZoomInRequested()
        }
        Rectangle {
            visible: root.hasVideo
            Layout.preferredWidth: 1
            Layout.preferredHeight: 20
            color: Theme.divider
        }
        Repeater {
            model: [-30, -15, 15, 30]
            delegate: StudioSeekButton {
                required property int modelData
                objectName: "manualSeek" + modelData
                visible: root.hasVideo
                controlSize: root.toolControlSize
                offsetSeconds: modelData
                onClicked: root.seekRequested(modelData)
            }
        }
        StudioIconButton {
            objectName: "manualSplitResultButton"
            visible: root.hasVideo
            controlSize: root.toolControlSize
            iconName: "split"
            toolTipText: qsTr("Chia đoạn tại vị trí phát (S)")
            showToolTip: true
            onClicked: root.resultSplitRequested()
        }
    }

    RowLayout {
        id: outputGroup
        objectName: "manualOutputControlsGroup"
        anchors.right: parent.right
        anchors.rightMargin: Theme.space12
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.space8

        OutputFrameCombo {
            id: frameCombo
            objectName: "manualOutputFrameCombo"
            visible: root.hasVideo
            Layout.preferredWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            enabled: root.outputFormatEditable
            outputFormat: root.outputFormat
            popup.width: Math.max(frameCombo.width, 220)
            onEdited: function(value) { root.outputFormatEdited(value); }
        }
        OutputSpeedButton {
            objectName: "manualOutputSpeedButton"
            compactLabel: root.compactTools
            visible: root.hasVideo
            enabled: root.outputFormatEditable
            speed: root.outputSpeed
            onEdited: function(value) { root.outputSpeedEdited(value); }
        }
        StudioButton {
            objectName: "manualExportButton"
            visible: root.hasVideo
            enabled: root.exportBusy || root.exportEnabled
            text: root.exportBusy ? qsTr("Đang xuất") : qsTr("Xuất")
            iconName: "open"
            variant: "primary"
            onClicked: {
                if (root.exportBusy)
                    root.exportProgressRequested();
                else
                    root.exportRequested();
            }
        }

        ProjectHeaderActions {
            projectFolderEnabled: root.hasProject
            showInputVideo: true
            inputVideoEnabled: root.hasVideo
            showVideoFolder: false
            videoFolderEnabled: root.hasVideo
            showTechnicalLog: true
            technicalLogEnabled: root.hasVideo
            deleteEnabled: root.hasProject
            onProjectFolderRequested: root.projectFolderRequested()
            onInputVideoRequested: root.inputVideoRequested()
            onVideoFolderRequested: root.videoFolderRequested()
            onTechnicalLogRequested: root.technicalLogRequested()
            onDeleteRequested: root.projectDeleteRequested()
        }
    }
}
