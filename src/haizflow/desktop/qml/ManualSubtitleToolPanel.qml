pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property var inspector
    property string currentTab: "content"
    readonly property var segment: inspector.selectedSubtitle
    readonly property string segmentId: segment ? String(segment.segment_id || "") : ""
    readonly property var draft: inspector.subtitleDrafts[segmentId] || null
    readonly property bool writable: inspector.editable && !inspector.taskQueued
    height: Math.max(320, inspector.panelBodyHeight)
    spacing: Theme.space8

    function focusEditor() {
        currentTab = "content";
        subtitleEditor.focusEditor();
    }
    function dismissEditor() { subtitleEditor.dismiss(); }
    function reloadText() {
        const pending = inspector.subtitleDrafts[segmentId];
        const saved = segment ? String(segment.text || "") : "";
        subtitleEditor.restoreDraft(saved, segment ? Number(segment.revision || 0) : 0,
            pending ? String(pending.text || "") : saved);
    }
    function selectAdjacent(delta) {
        if (subtitleEditor.saveStatus === "saving" || !inspector.subtitleSegments.length)
            return;
        subtitleEditor.dismiss();
        inspector.subtitleDialogSelectionRequested(Math.max(0,
            Math.min(inspector.subtitleSegments.length - 1, inspector.selectedSubtitleIndex + delta)));
        Qt.callLater(root.focusEditor);
    }

    Shortcut {
        sequence: "Ctrl+F"
        enabled: root.visible && root.currentTab === "content" && !root.inspector.expandedSubtitleEditorVisible
        onActivated: cueList.focusSearch()
    }
    Shortcut {
        sequence: "Alt+Up"
        enabled: root.visible && root.currentTab === "content" && !root.inspector.expandedSubtitleEditorVisible
        onActivated: root.selectAdjacent(-1)
    }
    Shortcut {
        sequence: "Alt+Down"
        enabled: root.visible && root.currentTab === "content" && !root.inspector.expandedSubtitleEditorVisible
        onActivated: root.selectAdjacent(1)
    }

    SegmentedControl {
        objectName: "manualSubtitleTabs"
        Layout.fillWidth: true
        options: [{value: "content", label: qsTr("Nội dung")}, {value: "style", label: qsTr("Kiểu chữ")}]
        currentValue: root.currentTab
        onActivated: value => root.currentTab = value
    }
    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        visible: root.currentTab === "content"
        spacing: Theme.space8
        SubtitleCueList {
            id: cueList
            Layout.fillWidth: true
            Layout.fillHeight: true
            segments: root.inspector.subtitleSegments
            selectedIndex: root.inspector.selectedSubtitleIndex
            position: root.inspector.playheadSeconds
            navigationEnabled: subtitleEditor.saveStatus !== "saving"
            onSegmentSelected: index => {
                subtitleEditor.dismiss();
                root.inspector.subtitleDialogSelectionRequested(index);
            }
            onSegmentActivated: index => {
                subtitleEditor.dismiss();
                root.inspector.subtitleDialogSelectionRequested(index);
                Qt.callLater(root.focusEditor);
            }
        }
        SubtitleTextEditor {
            id: subtitleEditor
            objectName: "manualInlineSubtitleEditor"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(72, Math.min(104, root.height * 0.2))
            Layout.minimumHeight: 64
            Layout.maximumHeight: 104
            enabled: root.writable
            sessionActive: !root.inspector.expandedSubtitleEditorVisible
            segmentId: root.segmentId
            savedText: root.segment ? String(root.segment.text || "") : ""
            revision: root.segment ? Number(root.segment.revision || 0) : 0
            hasInitialDraft: root.draft !== null
            initialDraftText: root.draft ? String(root.draft.text || "") : ""
            minimumEditorHeight: 64
            onCommitRequested: (id, text, revision, request) => AppController.saveManualSubtitleText(id, text, revision, request)
            onDraftChanged: (id, text, revision) => root.inspector.rememberSubtitleDraft(id, text, revision)
            onDraftCleared: id => root.inspector.clearSubtitleDraft(id)
        }
        Text {
            Layout.fillWidth: true
            visible: subtitleEditor.saveStatus === "error" || subtitleEditor.saveStatus === "saving"
            text: subtitleEditor.saveStatus === "error" ? subtitleEditor.errorMessage : qsTr("Đang lưu…")
            color: subtitleEditor.saveStatus === "error" ? Theme.danger : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space4
            StudioIconButton {
                objectName: "manualSubtitleActionsButton"
                iconName: "more"
                toolTipText: qsTr("Thao tác phụ đề")
                enabled: root.writable && root.segment !== null && subtitleEditor.saveStatus !== "saving"
                onClicked: actions.visible ? actions.close() : actions.open()
                TopBarPopupMenu {
                    id: actions
                    objectName: "manualSubtitleActionsMenu"
                    menuContentWidth: 200
                    AppMenuItem {
                        text: qsTr("Tìm và thay thế")
                        onTriggered: root.inspector.openExpandedTextEditor(true)
                    }
                    MenuSeparator {}
                    AppMenuItem {
                        objectName: "manualSubtitleSplitAction"
                        text: qsTr("Tách tại con trỏ phát")
                        enabled: root.writable && subtitleEditor.saveStatus === "saved" && root.segment !== null
                            && root.inspector.playheadSeconds > Number(root.segment.start) + 0.12
                            && root.inspector.playheadSeconds < Number(root.segment.end) - 0.12
                        onTriggered: AppController.splitSubtitleSegment(root.segmentId, Math.round(root.inspector.playheadSeconds * 1000))
                    }
                    AppMenuItem {
                        objectName: "manualSubtitleMergeAction"
                        text: qsTr("Gộp với câu sau")
                        enabled: root.writable && subtitleEditor.saveStatus === "saved"
                            && root.inspector.selectedSubtitleIndex < root.inspector.subtitleSegments.length - 1
                        onTriggered: AppController.mergeSubtitleWithNext(root.segmentId)
                    }
                    MenuSeparator {}
                    AppMenuItem {
                        objectName: "manualSubtitleDeleteAction"
                        text: qsTr("Xóa phụ đề")
                        tone: "danger"
                        enabled: root.writable && subtitleEditor.saveStatus === "saved"
                        onTriggered: AppController.deleteSubtitleSegment(root.segmentId)
                    }
                }
            }
            StudioIconButton {
                objectName: "manualSubtitleExpandButton"
                iconName: "fullscreen"
                toolTipText: qsTr("Mở rộng")
                showToolTip: true
                enabled: root.segment !== null && subtitleEditor.saveStatus !== "saving"
                onClicked: root.inspector.openExpandedTextEditor(false)
            }
            StudioButton {
                text: qsTr("Bỏ thay đổi")
                variant: "ghost"
                visible: subtitleEditor.hasChanges || subtitleEditor.saveStatus === "error"
                enabled: subtitleEditor.saveStatus !== "saving"
                onClicked: subtitleEditor.discard()
            }
            Item { Layout.fillWidth: true }
            StudioButton {
                objectName: "manualInlineSubtitleSaveButton"
                text: subtitleEditor.saveStatus === "error" ? qsTr("Thử lưu") : qsTr("Lưu")
                variant: "primary"
                enabled: root.writable && subtitleEditor.canSave
                onClicked: subtitleEditor.apply()
            }
        }
    }
    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        visible: root.currentTab === "style"
        Loader {
            Layout.fillWidth: true
            active: root.currentTab === "style"
            sourceComponent: Component {
                ManualSubtitleStyleControls {
                    editable: root.writable
                    onStyleCommitted: root.inspector.settingsCommitted()
                }
            }
        }
        Item { Layout.fillHeight: true }
    }
}
