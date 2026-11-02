pragma ComponentBehavior: Bound
// qmllint disable missing-property
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root
    property string selectedModel: "q4"
    property string activeProvider: ""
    property string activeConnection: ""
    property string requestOwner: ""
    readonly property var api: AppController.translationApi || null
    readonly property var profiles: api ? api.profiles : []
    readonly property var providers: [
        {label: "HY-MT2", value: "hymt2"}, {label: "Gemini", value: "gemini"},
        {label: "OpenAI", value: "openai"}, {label: "DeepSeek", value: "deepseek"},
        {label: "OpenRouter", value: "openrouter"}, {label: qsTr("API tùy chỉnh"), value: "custom"}
    ]
    readonly property var localModels: [
        {label: qsTr("HY-MT2 CPU · Q4"), value: "q4"},
        {label: qsTr("HY-MT2 GPU · đầy đủ"), value: "full"}
    ]
    readonly property var geminiModels: [
        {label: qsTr("Gemini 3.1 Flash-Lite · giá thấp"), value: "gemini-3.1-flash-lite"},
        {label: qsTr("Gemini 3.5 Flash-Lite · tiết kiệm"), value: "gemini-3.5-flash-lite"},
        {label: qsTr("Gemini 3.8 Flash · chất lượng cao"), value: "gemini-3.8-flash", available: false}
    ]
    readonly property bool externalProvider: activeProvider.length > 0 && activeProvider !== "hymt2" && activeProvider !== "gemini"
    readonly property int rowHeight: externalProvider ? 56 : 44
    readonly property var connections: profiles.filter(function(row) { return row.provider === root.activeProvider; })
    readonly property bool connectionExists: connections.some(function(row) { return row.id === root.activeConnection; })
    readonly property bool ownCatalog: api && api.catalogConnection === activeConnection && connectionExists
    readonly property string catalogState: ownCatalog ? api.catalogState : "idle"
    readonly property var modelOptions: activeProvider === "hymt2" ? localModels
        : activeProvider === "gemini" ? geminiModels
        : !connectionExists || !api ? []
        : connectionOptions()
    readonly property string searchQuery: modelSearch.text.trim().toLowerCase()
    readonly property var visibleOptions: activeProvider.length === 0 ? providers
        : activeProvider !== "openrouter" || searchQuery.length === 0 ? modelOptions
        : modelOptions.filter(function(row) {
            return (String(row.label) + " " + String(row.value)).toLowerCase().indexOf(root.searchQuery) >= 0;
        })
    onVisibleOptionsChanged: Qt.callLater(root.resetListPosition)
    readonly property string displayText: {
        if (selectedModel.indexOf("api:") === 0) {
            const identifier = selectedModel.split(":")[1];
            return api && profiles.some(function(row) { return row.id === identifier; })
                ? api.choiceLabel(selectedModel) : qsTr("Kết nối dịch không còn trên máy");
        }
        for (const row of localModels.concat(geminiModels)) {
            if (row.value === selectedModel) return row.label;
        }
        return selectedModel === "auto" ? localModels[0].label : selectedModel;
    }
    readonly property int currentIndex: selectedModel.indexOf("gemini-") === 0 ? 1
        : selectedModel.indexOf("api:") === 0 && api ? providerIndex(selectedModel.split(":")[1]) : 0
    readonly property string currentValue: selectedModel
    readonly property string selectedApiModel: {
        const pieces = selectedModel.split(":");
        if (pieces.length > 2) return pieces.slice(2).join(":").split("#")[0];
        for (const row of profiles) {
            if (row.id === pieces[1]) return row.model;
        }
        return "";
    }
    signal edited(string value)
    signal setupRequested(string provider)
    implicitHeight: UiMetrics.controlHeight

    function providerIndex(connectionId) {
        for (const row of profiles) {
            if (row.id === connectionId) {
                for (let index = 0; index < providers.length; index++)
                    if (providers[index].value === row.provider) return index;
            }
        }
        return -1;
    }
    function connectionOptions() {
        const options = (ownCatalog && (catalogState === "ready" || catalogState === "partial")
            ? api.catalogOptions : api.connectionModels(activeConnection)).slice();
        if (activeProvider !== "openrouter" && selectedModel.split(":")[1] === activeConnection && selectedApiModel
                && !options.some(function(row) { return row.value === root.selectedApiModel; }))
            options.unshift({label: selectedApiModel, value: selectedApiModel});
        if (activeProvider === "openrouter")
            options.sort(function(left, right) {
                const priority = Number(right.pricing_kind === "free") - Number(left.pricing_kind === "free");
                return priority || String(left.label).toLowerCase().localeCompare(String(right.label).toLowerCase())
                    || String(left.value).localeCompare(String(right.value));
            });
        return options;
    }
    function resetListPosition() {
        if (!popup.visible) return;
        const selectedValue = externalProvider
            ? selectedModel.split(":")[1] === activeConnection ? selectedApiModel : ""
            : selectedModel;
        const index = activeProvider ? visibleOptions.findIndex(function(row) {
            return row.value === selectedValue;
        }) : currentIndex;
        list.cancelFlick();
        list.currentIndex = Math.max(0, index);
        list.forceLayout();
        if (activeProvider && index >= 0)
            list.positionViewAtIndex(index, ListView.Center);
        else
            list.positionViewAtBeginning();
    }
    function openProvider(provider) {
        if (requestOwner && api && api.catalogConnection === requestOwner) api.resetModels();
        requestOwner = "";
        modelSearch.text = "";
        activeProvider = provider;
        const matches = profiles.filter(function(row) { return row.provider === provider; });
        const selectedId = selectedModel.indexOf("api:") === 0 ? selectedModel.split(":")[1] : "";
        activeConnection = matches.some(function(row) { return row.id === selectedId; })
            ? selectedId : matches.length ? matches[0].id : "";
        resetListPosition();
        Qt.callLater(root.resetListPosition);
        if (externalProvider && !connectionExists) setupApiButton.forceActiveFocus();
        else if (provider === "openrouter") modelSearch.forceActiveFocus();
        else list.forceActiveFocus();
    }
    function choose(index) {
        const option = visibleOptions[index];
        if (!option || option.available === false) return;
        if (!activeProvider) { openProvider(option.value); return; }
        const format = activeProvider === "custom" && selectedModel.split(":")[1] === activeConnection
            && selectedModel.indexOf("#") >= 0 ? selectedModel.split("#")[1] : "";
        const value = externalProvider ? api.modelChoice(activeConnection, option.value, format) : option.value;
        commit(value);
    }
    function commit(value) {
        if (!value) return;
        popup.close();
        displayButton.forceActiveFocus();
        if (value.indexOf("gemini-") === 0)
            AppController.showProjectSessionAlertOnce("gemini-cost", qsTr("Chi phí Gemini"),
                qsTr("Có thể tính phí khi bật thanh toán. Kiểm tra Billing trong AI Studio."), "information");
        else if (value.indexOf("api:") === 0)
            AppController.showProjectSessionAlertOnce("translation-api-cost", qsTr("Chi phí API dịch"),
                qsTr("Phụ đề và hướng dẫn được gửi tới nhà cung cấp đã chọn. API có thể tính phí theo mức sử dụng."), "information");
        edited(value);
    }
    function configureApi() {
        const provider = activeProvider;
        popup.close();
        Qt.callLater(function() { AppController.requestApiKeySettings(provider); });
        setupRequested(provider);
    }
    onVisibleChanged: { if (!visible) popup.close(); }
    onEnabledChanged: { if (!enabled) popup.close(); }
    Button {
        id: displayButton
        objectName: "projectTranslationModelButton"
        anchors.fill: parent
        leftPadding: 12
        rightPadding: 38
        Accessible.name: qsTr("Model dịch") + ": " + root.displayText
        contentItem: Text {
            text: root.displayText
            color: root.enabled ? Theme.text : Theme.textDisabled
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            textFormat: Text.PlainText
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: Theme.radiusSmall
            color: displayButton.hovered ? Theme.surfaceMuted : Theme.input
            border.width: displayButton.visualFocus ? 2 : 1
            border.color: displayButton.visualFocus ? Theme.controlFocus : Theme.outline
        }
        AppIcon {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            width: Theme.icon
            height: Theme.icon
            glyph: popup.visible ? "\uE70E" : "\uE70D"
            iconColor: Theme.textMuted
            iconSize: Theme.iconSmall
        }
        onClicked: popup.visible ? popup.close() : popup.open()
        Keys.onDownPressed: popup.open()
    }
    Popup {
        id: popup
        objectName: "projectTranslationModelPopup"
        y: root.height + 6
        width: Math.max(root.width, Math.min(360, Overlay.overlay ? Overlay.overlay.width - 24 : 360))
        x: root.width - width
        margins: 8
        height: Math.min(420, Math.max(100, root.visibleOptions.length * root.rowHeight
            + (root.activeProvider ? header.implicitHeight : 0) + 18),
            Overlay.overlay ? Math.max(100, Overlay.overlay.height - 24) : 420)
        padding: 6
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        onOpened: {
            root.activeProvider = "";
            root.resetListPosition();
            Qt.callLater(root.resetListPosition);
            list.forceActiveFocus();
        }
        onClosed: {
            if (root.requestOwner && root.api && root.api.catalogConnection === root.requestOwner)
                root.api.resetModels();
            root.requestOwner = "";
        }
        background: Rectangle { color: Theme.surfaceElevated; radius: Theme.radius; border.color: Theme.outlineStrong }
        contentItem: ColumnLayout {
            spacing: Theme.space8
            ColumnLayout {
                id: header
                Layout.fillWidth: true
                visible: root.activeProvider.length > 0
                spacing: Theme.space8
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space8
                    StudioIconButton {
                        objectName: "projectTranslationBackButton"
                        controlSize: 28
                        iconSize: Theme.iconSmall
                        iconName: "back"
                        toolTipText: qsTr("Quay lại")
                        showToolTip: true
                        onClicked: { root.activeProvider = ""; list.currentIndex = 0; list.forceActiveFocus(); }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.providers.filter(function(row) { return row.value === root.activeProvider; }).map(function(row) { return row.label; }).join("")
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.body
                        font.weight: Font.Medium
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                    StudioIconButton {
                        objectName: "projectTranslationLoadModelsButton"
                        controlSize: 28
                        iconSize: Theme.iconSmall
                        visible: root.externalProvider && root.connectionExists
                        enabled: root.catalogState !== "loading"
                        iconName: "refresh"
                        toolTipText: root.catalogState === "loading" ? qsTr("Đang tải…") : qsTr("Tải danh sách model")
                        showToolTip: true
                        onClicked: {
                            root.requestOwner = root.activeConnection;
                            root.api.loadConnectionModels(root.activeConnection);
                        }
                    }
                    StudioIconButton {
                        objectName: "projectTranslationManageKeyButton"
                        controlSize: 28
                        iconSize: Theme.iconSmall
                        visible: root.externalProvider && root.connectionExists
                        iconName: "settings"
                        toolTipText: qsTr("Quản lý API key")
                        showToolTip: true
                        onClicked: root.configureApi()
                    }
                }
                AppComboBox {
                    objectName: "projectTranslationConnectionPicker"
                    Layout.fillWidth: true
                    visible: root.externalProvider && root.connections.length > 1
                    model: root.connections
                    textRole: "label"
                    valueRole: "id"
                    currentIndex: root.connections.findIndex(function(row) { return row.id === root.activeConnection; })
                    onActivated: { root.activeConnection = String(currentValue); modelSearch.text = ""; list.currentIndex = 0; }
                }
                AppTextField {
                    id: modelSearch
                    objectName: "openRouterModelSearch"
                    Layout.fillWidth: true
                    visible: root.activeProvider === "openrouter" && root.connectionExists
                    placeholderText: qsTr("Tìm model")
                    accessibleName: qsTr("Tìm model OpenRouter")
                    onTextEdited: list.currentIndex = 0
                    onAccepted: root.choose(Math.max(0, list.currentIndex))
                    Keys.onDownPressed: list.forceActiveFocus()
                }
                StudioButton {
                    id: setupApiButton
                    objectName: "projectTranslationSetupButton"
                    Layout.fillWidth: true
                    visible: root.externalProvider && !root.connectionExists
                    text: qsTr("Thêm API key")
                    onClicked: root.configureApi()
                }
                StudioButton {
                    objectName: "projectTranslationManualModelButton"
                    Layout.fillWidth: true
                    visible: root.externalProvider && root.connectionExists
                    text: qsTr("Nhập Model ID")
                    variant: "ghost"
                    onClicked: {
                        const identifier = root.activeConnection;
                        const profile = root.connections.find(function(row) { return row.id === identifier; });
                        if (!profile) return;
                        const modelId = root.selectedModel.split(":")[1] === identifier ? root.selectedApiModel : "";
                        const format = root.selectedModel.indexOf("#") >= 0 ? root.selectedModel.split("#")[1] : profile.format;
                        const custom = root.activeProvider === "custom";
                        popup.close();
                        manualLoader.invoke("openFor", [identifier, modelId, format, custom]);
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: root.catalogState === "loading" ? qsTr("Đang tải…")
                        : root.catalogState === "partial" ? qsTr("Đã tải một phần danh sách model.")
                        : ["auth", "error", "invalid", "unsupported"].indexOf(root.catalogState) !== -1
                            ? qsTr("Không tải được danh sách. Kiểm tra API key trong Cài đặt.")
                        : root.catalogState === "ready" && root.modelOptions.length === 0 ? qsTr("Không có model dịch phù hợp.")
                        : root.activeProvider === "openrouter" && root.searchQuery.length > 0
                            && root.visibleOptions.length === 0 ? qsTr("Không tìm thấy model")
                        : ""
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    wrapMode: Text.WordWrap
                }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.divider }
            }
            ListView {
                id: list
                objectName: "projectTranslationModelList"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                reuseItems: true
                keyNavigationEnabled: true
                highlightMoveDuration: 0
                highlightResizeDuration: 0
                model: root.visibleOptions
                delegate: ItemDelegate {
                    id: row
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    height: root.rowHeight
                    enabled: modelData.available !== false
                    highlighted: list.currentIndex === index
                    Accessible.name: modelData.label
                    readonly property bool chosen: root.activeProvider.length === 0 ? index === root.currentIndex
                        : root.externalProvider ? root.activeConnection === root.selectedModel.split(":")[1]
                            && modelData.value === root.selectedApiModel : modelData.value === root.selectedModel
                    contentItem: RowLayout {
                        spacing: Theme.space12
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                Layout.fillWidth: true
                                text: row.modelData.label
                                textFormat: Text.PlainText
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.body
                                color: row.enabled ? Theme.text : Theme.textDisabled
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: root.externalProvider
                                text: row.modelData.value
                                textFormat: Text.PlainText
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.metadata
                                color: Theme.textSubtle
                                elide: Text.ElideRight
                            }
                        }
                        Text {
                            objectName: "openRouterModelPricingLabel"
                            visible: root.activeProvider === "openrouter"
                            text: row.modelData.pricing_kind === "free" ? qsTr("Miễn phí")
                                : row.modelData.pricing_kind === "paid" ? qsTr("Tính phí") : qsTr("Chưa rõ phí")
                            color: row.modelData.pricing_kind === "free" ? Theme.success : Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.metadata
                            textFormat: Text.PlainText
                        }
                        AppIcon {
                            Layout.preferredWidth: Theme.iconSmall
                            Layout.preferredHeight: Theme.iconSmall
                            opacity: root.activeProvider.length === 0 || row.chosen ? 1 : 0
                            glyph: root.activeProvider.length === 0 ? "\uE76C" : "\uE73E"
                            iconColor: row.chosen ? Theme.interactive : Theme.textMuted
                            iconSize: Theme.iconSmall
                        }
                    }
                    background: Rectangle { radius: Theme.radiusSmall; color: row.highlighted || row.hovered ? Theme.interactiveMuted : "transparent" }
                    onClicked: root.choose(index)
                }
                Keys.onReturnPressed: root.choose(currentIndex)
                Keys.onRightPressed: { if (!root.activeProvider) root.choose(currentIndex); }
                Keys.onLeftPressed: { root.activeProvider = ""; list.currentIndex = 0; }
                Keys.onEscapePressed: popup.close()
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }
        }
    }
    LazyDialogLoader {
        id: manualLoader
        sourceComponent: Component {
            TranslationProjectModelDialog {
                onModelSelected: function(identifier, modelId, outputFormat) {
                    const value = root.api.modelChoice(identifier, modelId, outputFormat);
                    if (value) { close(); root.commit(value); }
                }
                onClosed: manualLoader.release()
            }
        }
    }
}
