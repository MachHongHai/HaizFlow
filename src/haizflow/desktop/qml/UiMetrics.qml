pragma Singleton
import QtQuick

QtObject {
    property real viewportWidth: 1440
    property real viewportHeight: 900

    readonly property bool compact: viewportWidth <= 1240
    readonly property bool wide: viewportWidth >= 1800
    readonly property int navigationCompact: 56
    readonly property int navigationExpanded: 204
    readonly property int pageMargin: compact ? 16 : wide ? 24 : 20
    readonly property int sectionGap: compact ? 12 : 16
    readonly property int controlHeight: 32
    readonly property int compactControlHeight: 30
    readonly property int primaryControlHeight: 34
    readonly property int inspectorMinimum: 280
    readonly property int inspectorPreferred: compact ? 280 : wide ? 320 : 296
    readonly property int toolbarHeight: 36
    readonly property int activityTrayHeight: 34
}
