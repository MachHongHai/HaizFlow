pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property string status: "pending"
    property string stepId: "queued"
    property string detail: ""
    property int progress: 0

    readonly property string phase: status === "pending" || stepId === "queued"
        ? "queued"
        : stepId === "waiting_for_models" || stepId === "starting"
            ? "preparing" : "running"
    readonly property bool measured: phase === "running" && [
        "manual_source", "manual_separation", "manual_recognition", "manual_audio",
        "extracting_audio", "separating_audio", "transcribing",
        "creating_subtitle", "building_audio_timeline"
    ].indexOf(stepId) < 0
    readonly property string phaseTitle: phase === "queued" ? qsTr("Đang chờ")
        : phase === "preparing" ? qsTr("Đang chuẩn bị") : qsTr("Đang xử lý")
    readonly property string phaseDetail: phase === "queued"
        ? qsTr("Tác vụ sẽ bắt đầu khi hàng đợi sẵn sàng.")
        : phase === "preparing"
            ? (stepId === "waiting_for_models"
                ? qsTr("Đang nạp model cần cho công cụ này.")
                : qsTr("Đang khởi tạo công cụ."))
            : I18n.progressDetail(detail)

    spacing: Theme.space4

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            text: root.phaseTitle
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }

        Text {
            visible: root.measured
            text: qsTr("%1%").arg(Math.max(0, Math.min(100, root.progress)))
            color: Theme.interactive
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }
    }

    Text {
        Layout.fillWidth: true
        visible: root.phaseDetail.length > 0
        text: root.phaseDetail
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        maximumLineCount: 2
        elide: Text.ElideRight
    }

    AppProgressBar {
        Layout.fillWidth: true
        visible: root.phase !== "queued"
        value: Math.max(0, Math.min(100, root.progress))
        indeterminate: !root.measured
        active: root.phase !== "queued"
    }
}
