pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root
    property var layers: []
    property string selectedId: "ocr-source-region"
    property bool editable: true
    readonly property var selectedLayer: layers.find(function(layer) {
        return String(layer.clip_id) === root.selectedId;
    }) || ({})
    signal layerSelected(string clipId)
    spacing: Theme.space4

    AppComboBox {
        objectName: "ocrLayerSelector"
        Layout.fillWidth: true
        enabled: root.layers.length > 0
        textRole: "label"
        valueRole: "value"
        model: root.layers.map(function(layer) {
            return {label: layer.primary ? qsTr("Vùng nhận diện")
                : I18n.progressDetail(String(layer.name || "")), value: String(layer.clip_id)};
        })
        currentIndex: root.layers.findIndex(function(layer) { return String(layer.clip_id) === root.selectedId; })
        onActivated: root.layerSelected(String(currentValue || ""))
    }
    StudioIconButton {
        objectName: "ocrLayerMenuButton"
        iconName: "more"
        enabled: root.editable && root.layers.length > 0
        onClicked: layerMenu.popup()
    }
    TopBarPopupMenu {
        id: layerMenu
        objectName: "ocrLayerMenu"
        menuContentWidth: 188
        AppMenuItem {
            text: root.selectedLayer.visible ? qsTr("Ẩn lớp") : qsTr("Hiện lớp")
            onTriggered: AppController.setTrackState(String(root.selectedLayer.track_id), "visible", !root.selectedLayer.visible)
        }
        AppMenuItem {
            collapsed: Boolean(root.selectedLayer.primary)
            text: qsTr("Xóa lớp")
            iconGlyph: IconCatalog.glyph("delete")
            onTriggered: AppController.removeClips([root.selectedId], false)
        }
    }
}
