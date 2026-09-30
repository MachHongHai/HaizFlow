pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property bool editable: true
    property bool hasMusic: false
    property bool loopMusic: true
    property bool ducking: false
    property int reductionDb: -12
    signal loopEdited(bool value)
    signal duckingEdited(bool value)
    signal reductionEdited(int value)
    signal musicRequired()
    spacing: Theme.space8

    Repeater {
        model: [qsTr("Lặp nhạc nền"), qsTr("Tự giảm nhạc khi có lời")]
        delegate: PropertyRow {
            id: row
            required property int index
            required property string modelData
            Layout.fillWidth: true
            label: modelData
            contentItem: Item {
                implicitWidth: 48
                implicitHeight: 30
                AppSwitch {
                    anchors.centerIn: parent
                    enabled: root.editable && root.hasMusic
                    opacity: root.hasMusic ? 1 : 0.45
                    checked: row.index === 0 ? root.loopMusic : root.ducking
                    onToggled: row.index === 0 ? root.loopEdited(checked) : root.duckingEdited(checked)
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: root.editable && !root.hasMusic
                    onClicked: root.musicRequired()
                }
            }
        }
    }
    PropertyRow {
        Layout.fillWidth: true
        visible: root.hasMusic && root.ducking
        label: qsTr("Mức giảm")
        contentItem: NumericField {
            enabled: root.editable
            from: -36; to: 0
            suffix: " dB"
            value: root.reductionDb
            onValueModified: root.reductionEdited(value)
        }
    }
}
