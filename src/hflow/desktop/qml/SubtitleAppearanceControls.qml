pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property var style: ({})
    signal changeRequested(var patch)
    readonly property var compactStyle: Object.assign({}, style, {
        "font_weight": style.bold ? 700 : 400,
        "outline_width": Number(style.outline ?? 2)
    })
    spacing: Theme.space12

    CompactTextStyleBar {
        objectName: "autoCompactSubtitleStyle"
        Layout.fillWidth: true
        style: root.compactStyle
        karaokeEnabled: true
        onChangeRequested: function (patch) {
            const mapped = Object.assign({}, patch);
            if (mapped.font_weight !== undefined) {
                mapped.bold = Number(mapped.font_weight) >= 600;
                delete mapped.font_weight;
            }
            if (mapped.outline_width !== undefined) {
                mapped.outline = mapped.outline_width;
                delete mapped.outline_width;
            }
            root.changeRequested(mapped);
        }
    }
}
