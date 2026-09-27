pragma ComponentBehavior: Bound

import QtQuick
import "."

AppComboBox {
    id: root
    property string selectedModel: "q4"
    signal edited(string value)
    textRole: "label"
    valueRole: "value"
    model: [
        { label: qsTr("CPU · HY-MT2 Q4"), value: "q4" },
        { label: qsTr("GPU · HY-MT2 đầy đủ"), value: "full" }
    ]
    currentIndex: root.selectedModel === "full" ? 1 : 0
    onActivated: {
        root.edited(root.currentValue);
        root.currentIndex = Qt.binding(function() {
            return root.selectedModel === "full" ? 1 : 0;
        });
    }
}
