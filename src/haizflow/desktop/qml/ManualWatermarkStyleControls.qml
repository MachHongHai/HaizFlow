pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

CompactTextStyleBar {
    id: root

    signal watermarkStyleEdited()

    maximumOutline: 6
    style: ({
        "text_color": AppController.watermarkTextColor,
        "font_weight": AppController.watermarkBold ? 700 : 400,
        "italic": AppController.watermarkItalic,
        "outline_width": Math.round(AppController.watermarkOutlinePercent / 50)
    })

    onChangeRequested: function(patch) {
        if (patch.text_color !== undefined)
            AppController.watermarkTextColor = String(patch.text_color);
        if (patch.font_weight !== undefined)
            AppController.watermarkBold = Number(patch.font_weight) >= 600;
        if (patch.italic !== undefined)
            AppController.watermarkItalic = Boolean(patch.italic);
        if (patch.outline_width !== undefined)
            AppController.watermarkOutlinePercent = Math.round(Number(patch.outline_width) * 50);
        root.watermarkStyleEdited();
    }
}
