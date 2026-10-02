import QtQuick
import QtQuick.Controls.Basic

// Discrete slider: a dot marks each step so the levels are visible.
Slider {
    id: control
    hoverEnabled: true
    opacity: enabled ? 1 : 0.45
    implicitHeight: 28
    background: Item {
        x: control.leftPadding; y: control.topPadding + control.availableHeight / 2 - 2
        width: control.availableWidth; height: 4
        Rectangle { anchors.fill: parent; radius: 2; color: theme.raised }
        Rectangle { width: control.visualPosition * parent.width; height: parent.height; radius: 2; color: theme.accent }
        Repeater {
            model: control.stepSize > 0 ? Math.round((control.to - control.from) / control.stepSize) + 1 : 0
            delegate: Rectangle {
                required property int index
                readonly property real at: index / Math.max(1, Math.round((control.to - control.from) / control.stepSize))
                x: at * (parent.width - 2) - 2; y: -2; width: 6; height: 6; radius: 3
                color: at <= control.visualPosition ? theme.accent : theme.sheen
            }
        }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: 18; height: 18; radius: 9
        color: control.pressed ? theme.accentHover : theme.text
        border.width: control.visualFocus ? 3 : 0; border.color: theme.accent
    }
}
