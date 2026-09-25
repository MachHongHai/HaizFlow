pragma ComponentBehavior: Bound

import QtQuick
import QtTest

import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 400
    height: 500

    Component {
        id: styleBarComponent
        CompactTextStyleBar {
            width: 340
            style: ({ "font_family": "Segoe UI", "font_weight": 400,
                "italic": false, "text_color": "#FFFFFF", "outline_width": 2 })
        }
    }

    SignalSpy {
        id: changeSpy
        signalName: "changeRequested"
    }

    TestCase {
        name: "CompactTextStyleBarTests"
        when: windowShown

        function test_compactControlsWithoutFontPicker() {
            const bar = createTemporaryObject(styleBarComponent, root);
            verify(!!bar);
            const fontSelector = findChild(bar, "compactFontSelector");
            const boldToggle = findChild(bar, "compactBoldToggle");
            const italicToggle = findChild(bar, "compactItalicToggle");
            const outlineWidth = findChild(bar, "compactOutlineWidth");
            verify(!fontSelector);
            verify(!!boldToggle);
            verify(!!italicToggle);
            verify(!!outlineWidth);
            compare(boldToggle.checked, false);
            compare(outlineWidth.value, 2);
            verify(italicToggle.x >= boldToggle.x + boldToggle.width);

            changeSpy.target = bar;
            changeSpy.clear();
            boldToggle.checked = true;
            boldToggle.toggled();
            tryCompare(changeSpy, "count", 1);
            compare(changeSpy.signalArguments[0][0].font_weight, 700);
        }
    }
}
