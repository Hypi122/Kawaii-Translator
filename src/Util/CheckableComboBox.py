"""
Warning: No humans were involved in the making of this file. 
That also means no creativity, wit, or anything resembling a good comment. 
You have been warned.
"""

from PyQt6.QtCore import Qt, QEvent, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import QComboBox

class CheckableComboBox(QComboBox):
    """
    A QComboBox subclass that allows multiple item selection using checkboxes.
    
    Emits a `selectionChanged` signal with a list of the text of checked items
    whenever the selection is modified.
    """
    selectionChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText("Select items...")

        # *** NEW: Install event filter on the line edit to capture clicks ***
        self.lineEdit().installEventFilter(self)
        
        self.model = QStandardItemModel()
        self.setModel(self.model)

        self.model.itemChanged.connect(self._update_text_and_emit_signal)

        self.view().viewport().installEventFilter(self)

        self._popup_should_hide = True

    def eventFilter(self, source, event):
        # *** NEW SECTION: Handle clicks on the line edit itself ***
        if source == self.lineEdit() and event.type() == QEvent.Type.MouseButtonPress:
            # Toggle the popup's visibility when the line edit is clicked
            if self.view().isVisible():
                self.hidePopup()
            else:
                self.showPopup()
            return True  # Event handled

        # --- Existing section: Handle clicks within the dropdown list ---
        if source == self.view().viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            index = self.view().indexAt(event.pos())
            if index.isValid():
                item = self.model.itemFromIndex(index)
                if item.isCheckable():
                    new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
                    item.setCheckState(new_state)
                    
                    self._popup_should_hide = False 
                    return True # Event handled
        
        # Pass all other events to the base class's eventFilter
        return super().eventFilter(source, event)

    def hidePopup(self):
        if self._popup_should_hide:
            super().hidePopup()
        self._popup_should_hide = True

    def addItem(self, text, userData=None, checked=False):
        item = QStandardItem(text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        if userData is not None:
            item.setData(userData, Qt.ItemDataRole.UserRole)
        self.model.appendRow(item)

    def addItems(self, texts):
        for text in texts:
            self.addItem(text)
            
    def clear(self):
        self.model.clear()
        self._update_text_and_emit_signal()

    def _update_text_and_emit_signal(self):
        checked_items = self.checkedItemsText()
        if checked_items:
            self.lineEdit().setText(", ".join(checked_items))
        else:
            self.lineEdit().setText("")
            self.lineEdit().setPlaceholderText("Select items...")
        
        self.selectionChanged.emit(checked_items)
        
    def checkedItemsText(self):
        return [self.model.item(i).text() for i in range(self.model.rowCount()) if self.model.item(i).checkState() == Qt.CheckState.Checked]
        
    def checkedItemsData(self, role=Qt.ItemDataRole.UserRole):
        return [self.model.item(i).data(role) for i in range(self.model.rowCount()) if self.model.item(i).checkState() == Qt.CheckState.Checked]

    def setCheckedItems(self, values_to_check, role=Qt.ItemDataRole.DisplayRole):
        lookup_set = set(values_to_check)
        self.model.blockSignals(True)
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            item_value = item.data(role)
            if item_value in lookup_set:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.model.blockSignals(False)
        self._update_text_and_emit_signal()