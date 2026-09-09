import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root
    width: 1120
    height: 720
    color: Theme.window

    Binding {
        target: UiMetrics
        property: "viewportWidth"
        value: root.width
    }

    Binding {
        target: UiMetrics
        property: "viewportHeight"
        value: root.height
    }

    Flickable {
        anchors.fill: parent
        anchors.margins: Theme.space24
        contentWidth: width
        contentHeight: gallery.implicitHeight + Theme.space24
        clip: true

        ColumnLayout {
            id: gallery
            width: parent.width
            spacing: Theme.space16

            SectionHeader {
                Layout.fillWidth: true
                title: "HaizFlow UI Gallery"
                subtitle: "Foundation controls and feedback states"
            }

            AppSurface {
                Layout.fillWidth: true
                SectionHeader { Layout.fillWidth: true; title: "Buttons" }
                RowLayout {
                    AppButton { text: "Primary"; tone: "primary" }
                    AppButton { text: "Secondary" }
                    AppButton { text: "Ghost"; tone: "ghost" }
                    AppButton { text: "Danger"; tone: "danger" }
                    AppButton { text: "Disabled"; enabled: false }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: UiMetrics.compact ? 1 : 2
                columnSpacing: Theme.space16
                rowSpacing: Theme.space16

                AppSurface {
                    Layout.fillWidth: true
                    SectionHeader { Layout.fillWidth: true; title: "Inputs" }
                    AppTextField { Layout.fillWidth: true; placeholderText: "Text field" }
                    SearchField { Layout.fillWidth: true }
                    AppComboBox { Layout.fillWidth: true; model: ["First", "Second", "Third"] }
                    AppTextArea { Layout.fillWidth: true; placeholderText: "Notes" }
                    RowLayout {
                        AppCheckBox { text: "Checked"; checked: true }
                        AppSwitch { text: "Enabled"; checked: true }
                    }
                }

                AppSurface {
                    Layout.fillWidth: true
                    SectionHeader { Layout.fillWidth: true; title: "Status" }
                    RowLayout {
                        StatusBadge { status: "ready"; label: "Ready" }
                        StatusBadge { status: "processing"; label: "Processing" }
                        StatusBadge { status: "done"; label: "Complete" }
                        StatusBadge { status: "failed"; label: "Failed" }
                    }
                    InlineBanner { Layout.fillWidth: true; tone: "info"; message: "Background model is ready." }
                    InlineBanner { Layout.fillWidth: true; tone: "warning"; message: "This operation may take longer on CPU." }
                    PreviewProgress { Layout.fillWidth: true; value: 0.64 }
                }
            }

            StickyCommandBar {
                Layout.fillWidth: true
                statusText: "Autosaved"
                AppButton { text: "Pause" }
                AppButton { text: "Export"; tone: "primary" }
            }
        }
    }
}
