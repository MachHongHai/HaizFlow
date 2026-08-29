pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    objectName: "projectSetupDialog"

    property string projectType: "single"

    preferredWidth: 560
    maximumWidth: 620
    title: projectType === "batch"
        ? qsTr("Dự án hàng loạt")
        : projectType === "manual"
            ? qsTr("Dự án thủ công")
            : projectType === "download"
                ? qsTr("Dự án tải xuống")
                : projectType === "publish"
                    ? qsTr("Dự án đăng mạng xã hội")
                    : qsTr("Dự án tự động")

    function openForType(type) {
        projectType = ["batch", "manual", "download", "publish"].includes(type)
            ? type : "single"
        open()
    }

    function submit() {
        const name = projectName.text.trim()
        if (name.length === 0 || AppController.projectDirectory.length === 0)
            return
        if (AppController.prepareProject(name, AppController.projectDirectory, root.projectType))
            root.close()
    }

    onOpened: {
        projectName.clear()
        projectName.forceActiveFocus()
    }

    FormSection {
        Layout.fillWidth: true
        title: qsTr("Tên dự án")

        StudioField {
            id: projectName
            objectName: "projectNameInput"
            Layout.fillWidth: true
            accessibleName: qsTr("Tên dự án")
            placeholderText: qsTr("Nhập tên dự án")
            selectByMouse: true
            Keys.onReturnPressed: root.submit()
        }
    }

    FormSection {
        Layout.fillWidth: true
        title: root.projectType === "download"
            ? qsTr("Thư mục tải xuống") : qsTr("Thư mục dự án")

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: UiMetrics.controlHeight
                radius: Theme.radiusSmall
                color: Theme.input
                border.width: 1
                border.color: Theme.outline

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space12
                    anchors.rightMargin: Theme.space12
                    text: AppController.projectDirectory
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    verticalAlignment: Text.AlignVCenter
                    textFormat: Text.PlainText
                    elide: Text.ElideMiddle
                }
            }

            StudioButton {
                text: qsTr("Chọn thư mục")
                iconName: "folder"
                onClicked: AppController.browseProjectDirectoryForType(root.projectType)
            }
        }
    }

    footerActions: [
        StudioButton {
            text: qsTr("Hủy")
            variant: "ghost"
            onClicked: root.close()
        },
        StudioButton {
            id: continueButton
            objectName: "continueProjectButton"
            text: qsTr("Tạo dự án")
            iconName: "forward"
            variant: "primary"
            enabled: projectName.text.trim().length > 0
                && AppController.projectDirectory.length > 0
            onClicked: root.submit()
        }
    ]
}
