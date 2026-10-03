pragma ComponentBehavior: Bound

import QtQuick
import "."

CompactTextStyleBar {
    id: root
    property var controller: AppController

    signal watermarkStyleEdited()

    maximumOutline: 6
    style: ({
        "text_color": root.controller.watermarkTextColor,
        "font_weight": root.controller.watermarkBold ? 700 : 400,
        "italic": root.controller.watermarkItalic,
        "outline_width": Math.round(root.controller.watermarkOutlinePercent / 50)
    })

    onChangeRequested: function(patch) {
        if (patch.text_color !== undefined)
            root.controller.watermarkTextColor = String(patch.text_color);
        if (patch.font_weight !== undefined)
            root.controller.watermarkBold = Number(patch.font_weight) >= 600;
        if (patch.italic !== undefined)
            root.controller.watermarkItalic = Boolean(patch.italic);
        if (patch.outline_width !== undefined)
            root.controller.watermarkOutlinePercent = Math.round(Number(patch.outline_width) * 50);
        root.watermarkStyleEdited();
    }
}
