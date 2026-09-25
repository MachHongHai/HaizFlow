import QtQuick
import "."

AppSpinBox {
    id: root

    property int scaleFactor: 1
    property string suffix: ""
    property real realValue: value / Math.max(1, scaleFactor)

    implicitWidth: 118
    implicitHeight: 36
    font.pixelSize: TypeScale.metadata
    textFromValue: function(value, locale) {
        return Number(value / Math.max(1, root.scaleFactor)).toLocaleString(
            locale, "f", root.scaleFactor > 1 ? 1 : 0) + root.suffix;
    }
    valueFromText: function(text, locale) {
        const normalized = String(text).replace(root.suffix, "").trim();
        return Math.round(Number.fromLocaleString(locale, normalized)
            * Math.max(1, root.scaleFactor));
    }
}
