import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Sidebar entry: icon and label, left aligned; the current page is marked.
Button {
    id: control
    property string glyph: "play"
    property bool selected: false
    implicitHeight: theme.height + 2
    leftPadding: 12; rightPadding: 12
    hoverEnabled: true
    opacity: enabled ? 1 : 0.45
    contentItem: RowLayout {
        spacing: 11
        FIcon {
            kind: control.glyph; ink: control.selected ? theme.accent : theme.muted
            knockout: control.selected ? theme.raised : control.hovered ? theme.surface : theme.bg
            Layout.preferredWidth: 18; Layout.preferredHeight: 18
        }
        FText {
            text: control.text; Layout.fillWidth: true; elide: Text.ElideRight; maximumLineCount: 1
            font.weight: control.selected ? Font.DemiBold : Font.Medium
            color: control.selected ? theme.text : control.hovered ? theme.text : theme.muted
        }
    }
    background: Rectangle {
        radius: theme.radiusSm
        color: control.selected ? theme.raised : control.hovered ? theme.surface : "transparent"
        border.width: control.visualFocus ? 2 : 0; border.color: theme.accentHover
        Behavior on color { ColorAnimation { duration: 140 } }
        Rectangle { visible: control.selected; width: 3; height: 18; radius: 2; color: theme.accent; x: 0; anchors.verticalCenter: parent.verticalCenter }
    }
    Accessible.name: text
}
