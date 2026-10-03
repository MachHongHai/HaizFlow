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
        { label: qsTr("HY-MT2 CPU · Q4"), value: "q4" },
        { label: qsTr("HY-MT2 GPU · đầy đủ"), value: "full", available: AppController.processingDevice === "gpu" },
        { label: qsTr("Gemini 3.1 Flash-Lite · giá thấp"), value: "gemini-3.1-flash-lite" },
        { label: qsTr("Gemini 3.5 Flash-Lite · tiết kiệm"), value: "gemini-3.5-flash-lite" },
        { label: qsTr("Gemini 3.8 Flash · chất lượng cao"), value: "gemini-3.8-flash" }
    ]
    currentIndex: root.selectedModel === "full" ? 1
        : root.selectedModel === "gemini-3.1-flash-lite" ? 2
        : root.selectedModel === "gemini-3.5-flash-lite" ? 3
        : root.selectedModel === "gemini-3.8-flash" ? 4 : 0
    onActivated: {
        if (String(root.currentValue).indexOf("gemini-") === 0)
            AppController.showAppAlert(qsTr("Chi phí Gemini"),
                qsTr("Có thể tính phí khi bật thanh toán. Kiểm tra Billing trong AI Studio."), "information");
        root.edited(root.currentValue);
        root.currentIndex = Qt.binding(function() {
            return root.selectedModel === "full" ? 1
                : root.selectedModel === "gemini-3.1-flash-lite" ? 2
                : root.selectedModel === "gemini-3.5-flash-lite" ? 3
                : root.selectedModel === "gemini-3.8-flash" ? 4 : 0;
        });
    }
}
