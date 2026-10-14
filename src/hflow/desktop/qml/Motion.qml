pragma Singleton
import QtQuick

QtObject {
    readonly property int fast: 90
    readonly property int standard: 140
    readonly property int slow: 180
    readonly property int enterEasing: Easing.OutCubic
    readonly property int exitEasing: Easing.InCubic
}
