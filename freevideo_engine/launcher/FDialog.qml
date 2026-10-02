import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic

// A short question with one confirming action.
FPopup {
    id: dialog
    property string title: ""
    property string text: ""
    property string acceptText: "OK"
    property string rejectText: ""
    property bool destructive: false
    signal accepted()
    signal rejected()
    // Escape or an outside click counts as the non-confirming answer.
    property bool answered: false
    onAboutToShow: answered = false
    onClosed: if (!answered) rejected()
    width: Math.min(460, (parent ? parent.width : 500) - 40)
    closePolicy: rejectText ? Popup.CloseOnEscape : Popup.NoAutoClose
    contentItem: ColumnLayout {
        spacing: 12
        FText { text: dialog.title; font.pixelSize: theme.section; font.weight: Font.DemiBold; Layout.fillWidth: true }
        FText { text: dialog.text; color: theme.muted; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true; Layout.topMargin: 12; spacing: 8
            Item { Layout.fillWidth: true }
            FButton { visible: !!dialog.rejectText; text: dialog.rejectText; flat: true; onClicked: dialog.close() }
            FButton { text: dialog.acceptText; primary: !dialog.destructive; danger: dialog.destructive; onClicked: { dialog.answered = true; dialog.accepted(); dialog.close() } }
        }
    }
}
