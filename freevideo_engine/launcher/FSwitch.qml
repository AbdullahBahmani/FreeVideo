import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// A setting that is on or off: title and optional detail on the left, the
// switch on the right, as in a settings list. Consent stays an FCheck.
Switch {
    id: control
    property string detail: ""
    spacing: 16
    padding: 2
    hoverEnabled: true
    opacity: enabled ? 1 : 0.5
    indicator: Rectangle {
        x: control.width - width - control.rightPadding
        y: control.topPadding + (control.availableHeight - height) / 2
        implicitWidth: 38; implicitHeight: 22; radius: 11
        color: control.checked ? theme.accent : theme.hover
        border.width: control.checked ? 0 : 1; border.color: theme.sheen
        Behavior on color { ColorAnimation { duration: 140 } }
        Rectangle {
            width: 18; height: 18; radius: 9; y: 2
            x: control.checked ? parent.width - width - 2 : 2
            color: control.checked ? "#ffffff" : theme.text
            Behavior on x { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        }
        Rectangle {
            visible: control.visualFocus; anchors.fill: parent; anchors.margins: -3
            radius: 14; color: "transparent"; border.width: 2; border.color: theme.accentHover
        }
    }
    contentItem: ColumnLayout {
        spacing: 2
        FText { text: control.text; Layout.fillWidth: true; Layout.rightMargin: control.indicator.width + control.spacing; color: control.enabled ? theme.text : theme.disabled }
        FText { visible: !!control.detail; text: control.detail; font.pixelSize: theme.micro; color: theme.muted; Layout.fillWidth: true; Layout.rightMargin: control.indicator.width + control.spacing }
    }
}
