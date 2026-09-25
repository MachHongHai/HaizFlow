pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    objectName: "manualSubtitleEditorDialog"

    property QtObject controller: AppController
    property var segment: null
    property int selectedIndex: -1
    property int segmentCount: 0
    property bool hasInitialDraft: false
    property string initialDraftText: ""
    property bool findReplaceVisible: false
    property string replaceStatus: ""

    signal previousRequested()
    signal nextRequested()
    signal selectionRequested(int index)
    signal commitRequested(string segmentId, string text, int revision, string requestId)
    signal draftChanged(string segmentId, string text, int revision)
    signal draftCleared(string segmentId)
    signal editingClosed()
    signal deleteRequested(string segmentId)

    readonly property string segmentId: segment ? String(segment.segment_id || "") : ""
    readonly property string segmentText: segment ? String(segment.text || "") : ""
    readonly property int segmentRevision: segment ? Number(segment.revision || 0) : 0

    title: qsTr("Chỉnh nội dung phụ đề")
    subtitle: segment
        ? qsTr("%1 — %2")
            .arg(formatTime(Number(segment.start || 0)))
            .arg(formatTime(Number(segment.end || 0)))
        : qsTr("Chưa chọn phụ đề")
    preferredWidth: 900
    maximumWidth: 1080
    preferredHeight: 590
    maximumHeight: 720
    bodySpacing: Theme.space12

    function formatTime(secondsValue) {
        const totalMs = Math.max(0, Math.round((Number(secondsValue) || 0) * 1000));
        const minutes = Math.floor(totalMs / 60000);
        const seconds = Math.floor((totalMs % 60000) / 1000);
        const millis = totalMs % 1000;
        return String(minutes).padStart(2, "0") + ":"
            + String(seconds).padStart(2, "0") + "."
            + String(millis).padStart(3, "0");
    }

    function openForSelection() {
        open();
        Qt.callLater(subtitleEditor.focusEditor);
    }

    function closeEditor() {
        subtitleEditor.dismiss();
        close();
    }

    function findNext() {
        const query = findField.text;
        if (query.length === 0 || root.segmentCount <= 0)
            return;
        const items = AppController.manualEditorDocumentModel.subtitleSegments || [];
        const wanted = caseSensitiveSwitch.checked ? query : query.toLocaleLowerCase();
        for (let offset = 1; offset <= items.length; ++offset) {
            const index = (Math.max(0, root.selectedIndex) + offset) % items.length;
            const sourceText = String(items[index].text || "");
            const candidate = caseSensitiveSwitch.checked
                ? sourceText : sourceText.toLocaleLowerCase();
            if (candidate.indexOf(wanted) >= 0) {
                root.selectionRequested(index);
                return;
            }
        }
        root.replaceStatus = qsTr("Không tìm thấy nội dung phù hợp.");
    }

    function replaceText(replaceAll) {
        const changed = AppController.replaceSubtitleText(
            findField.text,
            replaceField.text,
            caseSensitiveSwitch.checked,
            replaceAll,
            replaceAll ? "" : root.segmentId);
        root.replaceStatus = changed > 0
            ? qsTr("Đã thay trong %1 đoạn.").arg(changed)
            : qsTr("Không có nội dung nào được thay.");
    }

    onClosed: root.editingClosed()

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space12

        Text {
            Layout.fillWidth: true
            text: root.segment
                ? qsTr("Đoạn %1 / %2").arg(root.selectedIndex + 1).arg(root.segmentCount)
                : qsTr("Chưa chọn phụ đề")
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.body
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }

        StudioIconButton {
            iconName: "search"
            toolTipText: qsTr("Tìm và thay thế")
            onClicked: {
                root.findReplaceVisible = !root.findReplaceVisible;
                if (root.findReplaceVisible)
                    Qt.callLater(findField.forceActiveFocus);
            }
        }

        StudioIconButton {
            iconName: "back"
            toolTipText: qsTr("Phụ đề trước")
            enabled: root.selectedIndex > 0
            onClicked: root.previousRequested()
        }

        StudioIconButton {
            iconName: "forward"
            toolTipText: qsTr("Phụ đề sau")
            enabled: root.selectedIndex >= 0 && root.selectedIndex < root.segmentCount - 1
            onClicked: root.nextRequested()
        }
    }

    InspectorSection {
        Layout.fillWidth: true
        visible: root.findReplaceVisible
        title: qsTr("Tìm và thay thế")
        collapsible: false

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            StudioField {
                id: findField
                Layout.fillWidth: true
                placeholderText: qsTr("Tìm trong phụ đề")
                onTextEdited: root.replaceStatus = ""
                Keys.onReturnPressed: root.findNext()
            }
            StudioButton {
                text: qsTr("Tìm tiếp")
                iconName: "forward"
                variant: "secondary"
                enabled: findField.text.length > 0
                onClicked: root.findNext()
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            StudioField {
                id: replaceField
                Layout.fillWidth: true
                placeholderText: qsTr("Thay bằng")
                onTextEdited: root.replaceStatus = ""
            }
            StudioButton {
                text: qsTr("Đoạn này")
                variant: "secondary"
                enabled: findField.text.length > 0 && root.segment
                    && subtitleEditor.saveStatus === "saved"
                onClicked: root.replaceText(false)
            }
            StudioButton {
                text: qsTr("Toàn bộ")
                variant: "primary"
                enabled: findField.text.length > 0
                    && subtitleEditor.saveStatus === "saved"
                onClicked: root.replaceText(true)
            }
        }
        RowLayout {
            Layout.fillWidth: true
            AppSwitch {
                id: caseSensitiveSwitch
                text: qsTr("Phân biệt chữ hoa/thường")
            }
            Item { Layout.fillWidth: true }
            Text {
                text: root.replaceStatus
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
            }
        }
    }

    SubtitleTextEditor {
        id: subtitleEditor
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 300
        controller: root.controller
        segmentId: root.segmentId
        savedText: root.segmentText
        revision: root.segmentRevision
        hasInitialDraft: root.hasInitialDraft
        initialDraftText: root.initialDraftText
        minimumEditorHeight: 300
        editorFontSize: 15
        onCommitRequested: function(id, text, version, request) {
            root.commitRequested(id, text, version, request);
        }
        onDraftChanged: function(id, text, version) {
            root.draftChanged(id, text, version);
        }
        onDraftCleared: function(id) { root.draftCleared(id); }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8
        StudioButton {
            text: qsTr("Xóa đoạn")
            iconName: "delete"
            variant: "danger"
            enabled: root.segment && subtitleEditor.saveStatus === "saved"
            onClicked: {
                root.deleteRequested(root.segmentId);
                root.close();
            }
        }
        Text {
            Layout.fillWidth: true
            visible: subtitleEditor.saveStatus !== "saved"
            text: subtitleEditor.saveStatus === "error"
                ? subtitleEditor.errorMessage || qsTr("Không lưu được")
                : subtitleEditor.saveStatus === "saving" ? qsTr("Đang lưu…")
                : qsTr("Chưa lưu")
            color: subtitleEditor.saveStatus === "error" ? Theme.danger : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }
        StudioButton {
            text: qsTr("Bỏ thay đổi")
            variant: "ghost"
            visible: subtitleEditor.saveStatus === "dirty" || subtitleEditor.saveStatus === "error"
            onClicked: subtitleEditor.discard()
        }
        StudioButton {
            objectName: "manualSubtitleSaveButton"
            text: subtitleEditor.saveStatus === "error" ? qsTr("Thử lưu") : qsTr("Lưu")
            variant: "primary"
            enabled: root.segment && subtitleEditor.saveStatus !== "saving"
                && subtitleEditor.saveStatus !== "saved"
            onClicked: subtitleEditor.apply()
        }
    }
}
