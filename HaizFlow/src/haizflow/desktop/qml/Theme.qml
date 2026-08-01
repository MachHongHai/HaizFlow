pragma Singleton
import QtQuick

QtObject {
    property bool darkMode: true
    property bool motionEnabled: true

    readonly property color window: darkMode ? "#0c1119" : "#f4f7fb"
    readonly property color surface: darkMode ? "#151b25" : "#ffffff"
    readonly property color surfaceElevated: darkMode ? "#1b2330" : "#f8fafc"
    readonly property color surfaceMuted: darkMode ? "#222c3a" : "#edf2f7"
    readonly property color surfaceStrong: darkMode ? "#2a3647" : "#dde5ef"
    readonly property color input: darkMode ? "#111823" : "#ffffff"
    readonly property color sidebar: darkMode ? "#090e16" : "#eaf0f7"
    readonly property color sidebarHover: darkMode ? "#131b27" : "#dfe8f2"
    readonly property color sidebarSelected: darkMode ? "#18262d" : "#ffffff"
    readonly property color topBar: darkMode ? "#111722" : "#f8fafc"
    readonly property color windowCaptionHover: darkMode ? "#222b38" : "#e8edf3"
    readonly property color windowCaptionPressed: darkMode ? "#2c3746" : "#d8e0e9"
    readonly property color windowCloseHover: "#c42b1c"
    readonly property color windowClosePressed: "#a4262c"
    readonly property color outline: darkMode ? "#2b3748" : "#cbd6e2"
    readonly property color outlineStrong: darkMode ? "#46566c" : "#98a9bc"
    readonly property color divider: darkMode ? "#243040" : "#dce5ee"

    readonly property color text: darkMode ? "#f2f5f9" : "#172334"
    readonly property color textMuted: darkMode ? "#aab6c5" : "#52657a"
    readonly property color textSubtle: darkMode ? "#78869a" : "#74869a"
    readonly property color textDisabled: darkMode ? "#5d6a7c" : "#94a2b2"
    readonly property color textOnAccent: darkMode ? "#07110f" : "#ffffff"
    readonly property color textOnDark: darkMode ? "#f5f7f9" : "#17212b"
    readonly property color textOnDarkMuted: darkMode ? "#a0aab7" : "#526273"

    readonly property color interactive: darkMode ? "#55d4c5" : "#0b7f75"
    readonly property color interactiveHover: darkMode ? "#74e0d4" : "#096f67"
    readonly property color interactivePressed: darkMode ? "#37b7a8" : "#075f58"
    readonly property color interactiveMuted: darkMode ? "#173a39" : "#dff5f1"
    readonly property color interactiveOutline: darkMode ? "#2a6863" : "#8bcfc5"
    readonly property color focus: darkMode ? "#80e6da" : "#078a7e"

    readonly property color blue: darkMode ? "#82b1ff" : "#2b63c7"
    readonly property color blueMuted: darkMode ? "#192f4d" : "#e6efff"
    readonly property color blueSurface: darkMode ? "#141e2e" : "#f1f6ff"
    readonly property color blueOutline: darkMode ? "#2c4a70" : "#a9c4ed"
    readonly property color violet: darkMode ? "#b6a0ff" : "#6847bd"
    readonly property color violetMuted: darkMode ? "#30264c" : "#eee9ff"
    readonly property color violetSurface: darkMode ? "#1c1929" : "#f7f4ff"
    readonly property color violetOutline: darkMode ? "#4b3e72" : "#c7b9ed"
    readonly property color amber: darkMode ? "#f2bd68" : "#a25f06"
    readonly property color amberMuted: darkMode ? "#49361d" : "#fff0d8"
    readonly property color warmSurface: darkMode ? "#251d17" : "#fff8ee"
    readonly property color danger: darkMode ? "#ff8275" : "#c93c32"
    readonly property color dangerMuted: darkMode ? "#47241f" : "#fbe5e2"
    readonly property color success: darkMode ? "#58d7a2" : "#16865c"
    readonly property color successMuted: darkMode ? "#17382d" : "#dcf3e9"
    readonly property color warning: darkMode ? "#f0c56b" : "#9a6500"
    readonly property color warningMuted: darkMode ? "#43371e" : "#f7ecd2"
    readonly property color scrim: darkMode ? "#b3000000" : "#660d1720"
    readonly property color video: "#050607"
    readonly property color codeSurface: darkMode ? "#090e15" : "#f2f5f9"
    readonly property color codeText: darkMode ? "#c4d1df" : "#34495e"
    readonly property color captionOverlay: darkMode ? "#d911151a" : "#d917212b"
    readonly property color captionText: "#ffffff"

    readonly property int radius: 8
    readonly property int radiusSmall: 6
    readonly property int radiusTiny: 4

    readonly property int space4: 4
    readonly property int space8: 8
    readonly property int space12: 12
    readonly property int space16: 16
    readonly property int space20: 20
    readonly property int space24: 24
    readonly property int space32: 32
    readonly property int gap: space16

    readonly property int label: 12
    readonly property int caption: 13
    readonly property int body: 15
    readonly property int bodyLarge: 16
    readonly property int h3: 18
    readonly property int h2: 21
    readonly property int h1: 28
    readonly property int display: 34

    readonly property int iconSmall: 15
    readonly property int icon: 18
    readonly property int iconLarge: 22
    readonly property string iconFont: "Segoe Fluent Icons"

    readonly property int motionFast: motionEnabled ? 100 : 0
    readonly property int motionStandard: motionEnabled ? 180 : 0
    readonly property int motionSlow: motionEnabled ? 260 : 0
    readonly property int navigationExpanded: 236
    readonly property int navigationCompact: 84
    readonly property int commandBarHeight: 62
}
