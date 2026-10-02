import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// One choice from a short list: [{value, label}]. Emits picked(value).
// Segments share the width equally; a raised pill slides to the current one.
Rectangle {
    id: group
    property var options: []
    property string current: ""
    property bool compact: false
    signal picked(string value)
    readonly property int currentIndex: {
        for (var i = 0; i < options.length; ++i)
            if (options[i].value === current) return i
        return -1
    }
    implicitHeight: compact ? theme.heightSm - 4 : theme.heightSm + 2
    implicitWidth: Math.max(1, options.length) * (compact ? 48 : 104) + 6
    radius: theme.radiusSm + 1; color: theme.bg; border.color: theme.border
    Rectangle {
        id: thumb
        visible: group.currentIndex >= 0
        readonly property real slot: (row.width - row.spacing * (group.options.length - 1)) / Math.max(1, group.options.length)
        x: row.x + group.currentIndex * (slot + row.spacing); y: row.y
        width: slot; height: row.height
        radius: theme.radiusSm - 2; color: theme.hover
        border.color: theme.sheen
        Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }
    RowLayout {
        id: row
        anchors.fill: parent; anchors.margins: 3; spacing: 2
        Repeater {
            model: group.options
            delegate: Button {
                id: segment
                required property var modelData
                required property int index
                readonly property bool active: group.currentIndex === index
                objectName: group.objectName ? group.objectName + "-" + modelData.value : ""
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 1
                padding: 0; leftPadding: group.compact ? 8 : 12; rightPadding: leftPadding
                hoverEnabled: true
                contentItem: Text {
                    text: segment.modelData.label
                    font.pixelSize: group.compact ? theme.micro : theme.body - 1
                    font.weight: segment.active ? Font.DemiBold : Font.Medium
                    color: segment.active || segment.hovered ? theme.text : theme.muted
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    Behavior on color { ColorAnimation { duration: 120 } }
                }
                background: Rectangle {
                    radius: theme.radiusSm - 2; color: "transparent"
                    border.width: segment.visualFocus ? 2 : 0; border.color: theme.accent
                }
                onClicked: group.picked(modelData.value)
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.label
                Accessible.checked: active
            }
        }
    }
}
