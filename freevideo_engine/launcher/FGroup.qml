import QtQuick
import QtQuick.Layouts

// A titled group of settings rows. Put FDivider between rows.
ColumnLayout {
    id: group
    default property alias contents: body.data
    property string title: ""
    spacing: 8
    FText { visible: !!group.title; text: group.title; font.pixelSize: theme.micro; font.weight: Font.DemiBold; color: theme.muted; Layout.leftMargin: 4 }
    Rectangle {
        Layout.fillWidth: true; implicitHeight: body.implicitHeight + 28
        radius: theme.radiusMd; color: theme.surface; border.color: theme.border
        ColumnLayout { id: body; x: 16; y: 14; width: parent.width - 32; spacing: 12 }
    }
}
