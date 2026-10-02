import QtQuick
import QtQuick.Layouts

Rectangle {
    id: card
    default property alias contents: body.data
    property int padding: 24
    property alias spacing: body.spacing
    // Cards that come and go with state (not with the page) settle in.
    property bool reveal: false
    implicitHeight: body.implicitHeight + padding * 2
    radius: theme.radiusMd; color: theme.surface; border.color: theme.border
    transform: Translate { id: shift }
    onVisibleChanged: if (visible && reveal) appear.restart()
    ParallelAnimation {
        id: appear
        NumberAnimation { target: card; property: "opacity"; from: 0; to: 1; duration: 220; easing.type: Easing.OutCubic }
        NumberAnimation { target: shift; property: "y"; from: 6; to: 0; duration: 300; easing.type: Easing.OutCubic }
    }
    ColumnLayout { id: body; x: card.padding; y: card.padding; width: parent.width-card.padding*2; spacing: 16 }
}
