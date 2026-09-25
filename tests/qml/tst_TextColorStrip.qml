pragma ComponentBehavior: Bound

import QtQuick
import QtTest

import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 400
    height: 300

    Component {
        id: stripComponent
        TextColorStrip {
            width: 270
            label: "Màu chữ"
            selectedColor: "#123456"
        }
    }

    SignalSpy {
        id: colorSpy
        signalName: "colorSelected"
    }

    TestCase {
        name: "TextColorStripTests"
        when: windowShown

        function test_rgbPickerStartsFromCurrentColorAndApplies() {
            const strip = createTemporaryObject(stripComponent, root);
            verify(!!strip);
            const button = findChild(strip, "customColorButton");
            const picker = findChild(strip, "rgbColorPopup");
            const apply = findChild(strip, "applyRgbColor");
            const hex = findChild(strip, "colorHexField");
            verify(!!button);
            verify(!!picker);
            verify(!!apply);
            verify(!!hex);
            colorSpy.target = strip;
            colorSpy.clear();

            button.clicked();
            tryCompare(picker, "opened", true);
            compare(picker.red, 18);
            compare(picker.green, 52);
            compare(picker.blue, 86);
            picker.setRgb(18, 128, 86);
            compare(picker.draftColor, "#128056");
            picker.setHsv(0, 1, 1);
            compare(picker.draftColor, "#FF0000");
            verify(picker.setHex("128056"));
            verify(!picker.setHex("not-a-color"));
            compare(picker.draftColor, "#128056");
            hex.text = picker.draftColor;
            apply.clicked();
            tryCompare(colorSpy, "count", 1);
            compare(colorSpy.signalArguments[0][0], "#128056");
        }
    }
}
