import QtQuick
import QtQuick.Controls.Basic

TextField {
    id: control
    implicitHeight: theme.height + 4
    color: theme.text; placeholderTextColor: theme.disabled
    selectionColor: theme.accentDim; selectedTextColor: theme.text
    font.pixelSize: theme.body
    leftPadding: 14; rightPadding: 14
    selectByMouse: true
    opacity: enabled ? 1 : 0.5
    background: Rectangle {
        radius: theme.radiusSm; color: theme.bg
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? theme.accent : control.hovered ? theme.sheen : theme.border
        Behavior on border.color { ColorAnimation { duration: 140 } }
    }
}
