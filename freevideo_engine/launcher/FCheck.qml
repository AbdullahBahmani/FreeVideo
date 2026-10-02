import QtQuick
import QtQuick.Controls.Basic

// Themed check box; the label wraps and stays aligned with the first line.
CheckBox {
    id: control
    spacing: 10
    padding: 4
    hoverEnabled: true
    opacity: enabled ? 1 : 0.5
    indicator: Rectangle {
        x: control.leftPadding; y: control.topPadding + 1
        implicitWidth: 18; implicitHeight: 18; radius: theme.radiusXs + 1
        color: control.checked ? theme.accent : control.hovered ? theme.raised : "transparent"
        border.width: control.checked ? 0 : 1.5
        border.color: control.visualFocus ? theme.accentHover : control.hovered ? theme.muted : theme.disabled
        Behavior on color { ColorAnimation { duration: 110 } }
        Canvas {
            anchors.fill: parent
            opacity: control.checked ? 1 : 0; scale: control.checked ? 1 : 0.5
            Behavior on opacity { NumberAnimation { duration: 120 } }
            Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.OutBack } }
            onPaint: {
                var c = getContext("2d"); c.reset()
                c.strokeStyle = theme.bg; c.lineWidth = 2; c.lineCap = "round"; c.lineJoin = "round"
                c.beginPath(); c.moveTo(4.5, 9.5); c.lineTo(7.8, 12.6); c.lineTo(13.5, 5.8); c.stroke()
            }
        }
        Rectangle {
            visible: control.visualFocus; anchors.fill: parent; anchors.margins: -3
            radius: theme.radiusXs + 4; color: "transparent"; border.width: 2; border.color: theme.accentHover
        }
    }
    contentItem: FText {
        text: control.text
        leftPadding: control.indicator.width + control.spacing
        font.pixelSize: theme.body - 1
        color: control.enabled ? theme.text : theme.disabled
    }
}
