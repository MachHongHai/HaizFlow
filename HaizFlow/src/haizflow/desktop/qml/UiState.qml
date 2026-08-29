pragma Singleton
import QtQuick

QtObject {
    readonly property string idle: "idle"
    readonly property string loading: "loading"
    readonly property string empty: "empty"
    readonly property string processing: "processing"
    readonly property string paused: "paused"
    readonly property string success: "success"
    readonly property string error: "error"
}
