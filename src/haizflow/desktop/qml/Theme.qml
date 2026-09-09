pragma Singleton
import QtQuick

QtObject {
    property bool motionEnabled: true

    readonly property string fontFamily: "Segoe UI Variable"

    // Warm Graphite Studio. Neutral surfaces carry hierarchy; copper is
    // reserved for direct interaction, focus and progress.
    readonly property color window: "#11100F"
    readonly property color surface: "#1B1A18"
    readonly property color surfaceElevated: "#211F1C"
    readonly property color surfaceMuted: "#292620"
    readonly property color surfaceStrong: "#302C27"
    readonly property color input: "#171614"
    readonly property color sidebar: "#161513"
    readonly property color sidebarHover: "#211F1C"
    readonly property color sidebarSelected: "#302820"
    readonly property color topBar: "#161513"
    readonly property color windowCaptionHover: "#292620"
    readonly property color windowCaptionPressed: "#332F2A"
    readonly property color windowCloseHover: "#c42b1c"
    readonly property color windowClosePressed: "#a4262c"
    readonly property color outline: "#48423A"
    readonly property color outlineStrong: "#665F55"
    readonly property color divider: "#332F2A"

    readonly property color text: "#F2EFE9"
    readonly property color textMuted: "#B8B1A6"
    readonly property color textSubtle: "#91897D"
    readonly property color textDisabled: "#797268"
    readonly property color textOnAccent: "#17120D"
    readonly property color textOnDark: "#F2EFE9"
    readonly property color textOnDarkMuted: "#B8B1A6"

    readonly property color interactive: "#C4915E"
    readonly property color interactiveHover: "#D4A16B"
    readonly property color interactivePressed: "#A9784A"
    readonly property color interactiveMuted: "#33271D"
    readonly property color interactiveOutline: "#7B5B3C"
    readonly property color focus: "#E2B47F"

    readonly property color amber: "#C29A57"
    readonly property color amberMuted: "#3B3020"
    readonly property color warmSurface: "#211F1C"
    readonly property color danger: "#C96F68"
    readonly property color dangerMuted: "#3D2421"
    readonly property color success: "#76A58A"
    readonly property color successMuted: "#22352A"
    readonly property color warning: "#C29A57"
    readonly property color warningMuted: "#3B3020"
    readonly property color scrim: "#b8000000"
    readonly property color video: "#080706"
    readonly property color codeSurface: "#0D0C0B"
    readonly property color codeText: "#D0CAC1"
    readonly property color captionOverlay: "#DC11100F"
    readonly property color captionText: "#FFFFFF"

    readonly property int radius: 6
    readonly property int radiusSmall: 4
    readonly property int radiusTiny: 4

    readonly property int space4: 4
    readonly property int space8: 8
    readonly property int space12: 12
    readonly property int space16: 16
    readonly property int space20: 20
    readonly property int space24: 24
    readonly property int space32: 32
    readonly property int gap: space16

    readonly property int label: TypeScale.metadata
    readonly property int caption: TypeScale.label
    readonly property int body: TypeScale.control
    readonly property int bodyLarge: TypeScale.body
    readonly property int h3: TypeScale.section
    readonly property int h2: TypeScale.title
    readonly property int h1: TypeScale.pageTitle
    readonly property int display: TypeScale.display

    readonly property int iconSmall: 14
    readonly property int icon: 16
    readonly property int iconLarge: 20
    readonly property string iconFont: "Segoe Fluent Icons"

    readonly property int motionFast: motionEnabled ? Motion.fast : 0
    readonly property int motionStandard: motionEnabled ? Motion.standard : 0
    readonly property int motionSlow: motionEnabled ? Motion.slow : 0
    readonly property int navigationExpanded: UiMetrics.navigationExpanded
    readonly property int navigationCompact: UiMetrics.navigationCompact
    readonly property int commandBarHeight: 48
}
