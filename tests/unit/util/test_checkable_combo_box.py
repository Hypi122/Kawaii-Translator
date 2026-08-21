import pytest
from PyQt6.QtCore import Qt, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QComboBox

from Util.CheckableComboBox import CheckableComboBox

@pytest.fixture
def combo(qtbot):
    widget = CheckableComboBox()
    qtbot.addWidget(widget)
    widget.show()
    return widget

class TestCheckableComboBoxInitialization:
    def test_initialization_has_correct_default_state(self, combo):
        assert combo.isEditable() is True
        assert combo.lineEdit().isReadOnly() is True
        assert combo.lineEdit().placeholderText() == "Select items..."
        assert combo.count() == 0

class TestCheckableComboBoxAddItems:
    def test_add_item_adds_singleitem(self, combo):
        combo.addItem("Item 1")
        assert combo.count() == 1

    def test_add_items_adds_multiple_items(self, combo):
        combo.addItems(["Item 1", "Item 2"])
        assert combo.count() == 2

    def test_add_item_checked_adds_checked_item_by_default(self, combo):
        combo.addItem("Checked Item", checked=True)
        assert combo.checkedItemsText() == ["Checked Item"]
        assert combo.lineEdit().text() == "Checked Item"

    def test_add_item_userdata_stores_user_data_correctly(self, combo):
        data_obj = {"id": 1}
        combo.addItem("Data Item", userData=data_obj, checked=True)
        assert combo.checkedItemsData() == [data_obj]

    def test_add_item_empty_string_adds_item_with_empty_text(self, combo):
        combo.addItem("")
        assert combo.count() == 1
        assert combo.itemText(0) == ""

    def test_add_item_with_none_userdata_handles_none_correctly(self, combo):
        combo.addItem("Item", userData=None, checked=True)
        assert combo.checkedItemsData() == [None]

class TestCheckableComboBoxSelection:
    def test_selection_changed_signal_and_text_updates_on_toggle(self, combo, qtbot):
        combo.addItems(["A", "B", "C"])

        # setCheckState stands in for the user ticking an item in the dropdown
        with qtbot.waitSignal(combo.selectionChanged) as blocker:
            combo.model.item(0).setCheckState(Qt.CheckState.Checked)

        assert blocker.args[0] == ["A"]
        assert combo.lineEdit().text() == "A"

        with qtbot.waitSignal(combo.selectionChanged) as blocker:
            combo.model.item(1).setCheckState(Qt.CheckState.Checked)

        assert blocker.args[0] == ["A", "B"]
        assert combo.lineEdit().text() == "A, B"

    def test_set_checked_items_display_role_sets_items_by_display_text(self, combo):
        combo.addItems(["A", "B", "C"])

        combo.setCheckedItems(["A", "C"])

        assert combo.checkedItemsText() == ["A", "C"]
        assert combo.lineEdit().text() == "A, C"

    def test_set_checked_items_user_role_sets_items_by_user_data(self, combo):
        combo.addItem("A", userData=1)
        combo.addItem("B", userData=2)
        combo.addItem("C", userData=3)

        # Check item with data 2 ("B")
        combo.setCheckedItems([2], role=Qt.ItemDataRole.UserRole)

        assert combo.checkedItemsText() == ["B"]
        assert combo.lineEdit().text() == "B"

    def test_set_checked_items_with_nonexistent_values_ignores_invalid_values(self, combo):
        combo.addItems(["A", "B", "C"])
        combo.setCheckedItems(["X", "Y", "Z"])
        
        assert combo.checkedItemsText() == []
        assert combo.lineEdit().text() == ""

    def test_set_checked_items_partial_match_sets_only_existing_values(self, combo):
        combo.addItems(["A", "B", "C"])
        combo.setCheckedItems(["A", "X", "C"])
        
        assert combo.checkedItemsText() == ["A", "C"]

    def test_checked_items_retrieval_returns_checked_items_text_and_data(self, combo):
        combo.addItem("A", userData=10, checked=True)
        combo.addItem("B", userData=20, checked=False)
        combo.addItem("C", userData=30, checked=True)
        
        assert combo.checkedItemsText() == ["A", "C"]
        assert combo.checkedItemsData() == [10, 30]

    def test_checked_items_data_empty_returns_empty_list(self, combo):
        combo.addItem("A", userData=10)
        assert combo.checkedItemsData() == []

    def test_handles_duplicate_names_correctly(self, combo):
        combo.addItem("Same", userData=1)
        combo.addItem("Same", userData=2)

        combo.setCheckedItems([1], role=Qt.ItemDataRole.UserRole)

        assert combo.checkedItemsText() == ["Same"]
        assert combo.checkedItemsData() == [1]

    def test_unchecking_all_shows_placeholder_clears_text_and_shows_placeholder(self, combo, qtbot):
        combo.addItem("A", checked=True)

        assert combo.lineEdit().text() == "A"
        
        combo.model.item(0).setCheckState(Qt.CheckState.Unchecked)
        
        assert combo.checkedItemsText() == []
        assert combo.lineEdit().text() == ""
        assert combo.lineEdit().placeholderText() == "Select items..."

    def test_unchecking_current_first_item_updates_text_when_others_stay_checked(self, combo):
        combo.addItems(["A", "B", "C"])
        combo.setCheckedItems(["A", "C"])

        combo.model.item(0).setCheckState(Qt.CheckState.Unchecked)

        assert combo.checkedItemsText() == ["C"]
        assert combo.lineEdit().text() == "C"

class TestCheckableComboBoxMouseInteraction:
    @staticmethod
    def _mouse_event(event_type, pos):
        pos = QPointF(pos)
        return QMouseEvent(event_type, pos, pos,
                           Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)

    def _laid_out_view(self, combo):
        view = combo.view()
        view.resize(200, 200)
        view.doItemsLayout()
        return view

    def test_toggle_click_then_dismissal_closes(self, combo, mocker):
        combo.addItems(["A", "B"])
        combo.setCheckedItems(["A"])
        view = self._laid_out_view(combo)
        item_center = view.visualRect(combo.model.item(1).index()).center()

        QApplication.sendEvent(view.viewport(), self._mouse_event(QEvent.Type.MouseButtonRelease, item_center))

        assert combo.checkedItemsText() == ["A", "B"]

        # A real popup never becomes visible headless, so "the popup closed"
        # is observed at the Qt boundary: the dismissal request must reach
        # QComboBox.hidePopup instead of being swallowed by our override.
        close_spy = mocker.patch.object(QComboBox, "hidePopup")
        combo.hidePopup()
        close_spy.assert_called_once()

    def test_disable_while_popup_open_suppresses_close_until_reenabled(self, combo, mocker):
        combo.addItems(["A", "B"])
        combo.showPopup()

        # While the app disabled the combo (engine swap in flight), close
        # attempts must be ignored; once re-enabled they must go through.
        close_spy = mocker.patch.object(QComboBox, "hidePopup")
        combo.setEnabled(False)
        combo.hidePopup()
        close_spy.assert_not_called()

        combo.setEnabled(True)
        combo.hidePopup()
        close_spy.assert_called_once()

class TestCheckableComboBoxClear:
    def test_clear_clears_all_items_and_emits_signal(self, combo, qtbot):
        combo.addItems(["A", "B"])
        combo.setCheckedItems(["A"])
        
        with qtbot.waitSignal(combo.selectionChanged) as blocker:
            combo.clear()

        assert combo.count() == 0
        assert combo.lineEdit().text() == ""
        assert combo.lineEdit().placeholderText() == "Select items..."
        assert blocker.args[0] == []