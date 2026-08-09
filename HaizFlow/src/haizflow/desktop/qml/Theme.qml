pragma Singleton
import QtQuick

QtObject {
    property bool motionEnabled: true

    // One graphite palette keeps every workspace visually consistent.  Cool
    // steel, violet and warm semantic accents add hierarchy without turning
    // the application into a single-colour surface.
    readonly property color window: "#0d1014"
    readonly property color surface: "#15191f"
    readonly property color surfaceElevated: "#1b2028"
    readonly property color surfaceMuted: "#232a33"
    readonly property color surfaceStrong: "#2d3540"
    readonly property color input: "#11161c"
    readonly property color sidebar: "#0a0d11"
    readonly property color sidebarHover: "#171c23"
    readonly property color sidebarSelected: "#20272f"
    readonly property color topBar: "#12161c"
    readonly property color windowCaptionHover: "#242a33"
    readonly property color windowCaptionPressed: "#303844"
    readonly property color windowCloseHover: "#c42b1c"
    readonly property color windowClosePressed: "#a4262c"
    readonly property color outline: "#303843"
    readonly property color outlineStrong: "#4b5664"
    readonly property color divider: "#272e37"

    readonly property color text: "#f1f3f5"
    readonly property color textMuted: "#abb3bd"
    readonly property color textSubtle: "#7f8996"
    readonly property color textDisabled: "#626b77"
    readonly property color textOnAccent: "#0b1117"
    readonly property color textOnDark: "#f6f7f8"
    readonly property color textOnDarkMuted: "#aab1ba"

    readonly property color interactive: "#84b7c8"
    readonly property color interactiveHover: "#9bc8d6"
    readonly property color interactivePressed: "#689cab"
    readonly property color interactiveMuted: "#20343b"
    readonly property color interactiveOutline: "#426876"
    readonly property color focus: "#a9d3df"

    readonly property color blue: "#8eb6e8"
    readonly property color blueMuted: "#213247"
    readonly property color blueSurface: "#171f2b"
    readonly property color blueOutline: "#3d5877"
    readonly property color violet: "#b8a4df"
    readonly property color violetMuted: "#332a46"
    readonly property color violetSurface: "#211d2a"
    readonly property color violetOutline: "#55486e"
    readonly property color amber: "#d9ad67"
    readonly property color amberMuted: "#49391f"
    readonly property color warmSurface: "#241f19"
    readonly property color danger: "#ef857d"
    readonly property color dangerMuted: "#472724"
    readonly property color success: "#70c99e"
    readonly property color successMuted: "#1d392d"
    readonly property color warning: "#d7b66c"
    readonly property color warningMuted: "#403821"
    readonly property color scrim: "#b8000000"
    readonly property color video: "#050607"
    readonly property color codeSurface: "#090c10"
    readonly property color codeText: "#c5ccd5"
    readonly property color captionOverlay: "#dc111419"
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
