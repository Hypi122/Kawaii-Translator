from PyQt6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QLabel, QFormLayout, QPushButton, QHBoxLayout, QLineEdit, QTabWidget, QGroupBox, QInputDialog, QMessageBox, QTextEdit
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QRunnable, QThreadPool, Qt
from PyQt6.QtGui import QKeySequence

from Util.CheckableComboBox import CheckableComboBox
from App.settings_service import settings_service

class WorkerSignals(QObject):
    """Signals from a running worker thread.

    finished
        No data
    """

    finished = pyqtSignal()

class Worker(QRunnable):
    finished = pyqtSignal()

    def __init__(self, fn, **kwargs):
        super().__init__()
        self.signals = WorkerSignals()
        self.fn = fn
        self.kwargs = kwargs

    @pyqtSlot()
    def run(self):
        try:
            self.fn(**self.kwargs)
        except Exception as err:
            print(f"Unexpected {err=}, {type(err)=}")
        finally:
            self.signals.finished.emit()


class SettingsTab(QWidget):
    def __init__(self, OcrManager, hotkey_manager, TranslationManager):
        super().__init__()
        self.OcrManager = OcrManager
        self.hotkey_manager = hotkey_manager
        self.TranslationManager = TranslationManager
        self.threadpool = QThreadPool()
        self.hotkey_inputs = {}
        self.setup_ui()
        self.load_settings()

        
    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Create tab widget for sub-tabs
        settings_tabs = QTabWidget()
        
        # General settings tab
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)

        # OCR Engine Settings
        ocrLayout = QVBoxLayout()
        self.ocrEngineLabel = QLabel("OCR Engine")
        self.ocrEngineBtn = QComboBox()
        self.ocrEngineBtn.addItems(self.OcrManager.available_engines())
        self.ocrEngineBtn.currentTextChanged.connect(self.start_change_ocr_engine)
        
        self.translateEngineLabel = QLabel("Translation Engines")
        self.translateEngineBtn = CheckableComboBox()
        self.translateEngineBtn.addItems(self.TranslationManager.available_engines())
        self.translateEngineBtn.selectionChanged.connect(self.start_change_translate_engine)
        
        # OCR Language Settings
        self.ocrLanguageLabel = QLabel("OCR Language")
        self.ocrLanguageInput = QLineEdit()
        
        # Translation Output Language Settings
        self.translationLanguageLabel = QLabel("Translation Output Language")
        self.translationLanguageInput = QLineEdit()
        
        # Translation Input Language Settings
        self.translationInputLanguageLabel = QLabel("Translation Input Language")
        self.translationInputLanguageInput = QLineEdit()
        
        ocrLayout.addWidget(self.ocrEngineLabel)
        ocrLayout.addWidget(self.ocrEngineBtn)
        ocrLayout.addWidget(self.translateEngineLabel)
        ocrLayout.addWidget(self.translateEngineBtn)
        ocrLayout.addWidget(self.ocrLanguageLabel)
        ocrLayout.addWidget(self.ocrLanguageInput)
        ocrLayout.addWidget(self.translationInputLanguageLabel)
        ocrLayout.addWidget(self.translationInputLanguageInput)
        ocrLayout.addWidget(self.translationLanguageLabel)
        ocrLayout.addWidget(self.translationLanguageInput)
        
        general_layout.addLayout(ocrLayout)

        # Hotkey Settings
        hotkeyLayout = QVBoxLayout()
        hotkeyLayout.addWidget(QLabel("Hotkey Settings"))
        
        self.hotkeyForm = QFormLayout()
        self.populate_hotkey_settings()
        hotkeyLayout.addLayout(self.hotkeyForm)
        
        general_layout.addLayout(hotkeyLayout)
        general_layout.addStretch()

        # OpenAI Settings tab
        openai_tab = QWidget()
        openai_layout = QVBoxLayout(openai_tab)
        
        # OCR Group Box
        ocr_group_box = QGroupBox("OCR")
        ocr_layout = QVBoxLayout()

        self.ocr_preset_btn = QComboBox()
        self.ocr_preset_btn.addItems(settings_service.get("ocr_presets"))
        self.ocr_preset_btn.currentTextChanged.connect(self.loadOpenaiSettings)

        ocr_preset_layout = QHBoxLayout()
        self.ocr_preset_create_btn = QPushButton("Create")
        self.ocr_preset_create_btn.clicked.connect(self.create_ocr_preset)
        self.ocr_preset_delete_btn = QPushButton("Delete")
        self.ocr_preset_delete_btn.clicked.connect(self.delete_ocr_preset)
        ocr_preset_layout.addWidget(self.ocr_preset_create_btn)
        ocr_preset_layout.addWidget(self.ocr_preset_delete_btn)

        self.openaiUrlOcrLabel = QLabel("OpenAI API URL")
        self.openaiUrlOcrInput = QLineEdit()
        
        self.openaiModelOcrLabel = QLabel("OpenAI Model")
        self.openaiModelOcrInput = QLineEdit()
        
        self.openaiKeyOcrLabel = QLabel("OpenAI API Key")
        self.openaiKeyOcrInput = QLineEdit()
        self.openaiKeyOcrInput.setEchoMode(QLineEdit.EchoMode.Password)
        
        ocr_layout.addWidget(self.ocr_preset_btn)
        ocr_layout.addLayout(ocr_preset_layout)
        ocr_layout.addWidget(self.openaiUrlOcrLabel)
        ocr_layout.addWidget(self.openaiUrlOcrInput)
        ocr_layout.addWidget(self.openaiModelOcrLabel)
        ocr_layout.addWidget(self.openaiModelOcrInput)
        ocr_layout.addWidget(self.openaiKeyOcrLabel)
        ocr_layout.addWidget(self.openaiKeyOcrInput)
        ocr_layout.addStretch()
        
        ocr_group_box.setLayout(ocr_layout)

        # Translation Group Box
        translation_group_box = QGroupBox("Translation")
        translation_layout = QVBoxLayout()
        
        
        self.translation_preset_btn = QComboBox()
        self.translation_preset_btn.addItems(settings_service.get("translation_presets"))
        self.translation_preset_btn.currentTextChanged.connect(self.loadOpenaiSettings)
        
        translation_preset_layout = QHBoxLayout()
        self.translation_preset_create_btn = QPushButton("Create")
        self.translation_preset_create_btn.clicked.connect(self.create_translation_preset)
        self.translation_preset_delete_btn = QPushButton("Delete")
        self.translation_preset_delete_btn.clicked.connect(self.delete_translation_preset)
        translation_preset_layout.addWidget(self.translation_preset_create_btn)
        translation_preset_layout.addWidget(self.translation_preset_delete_btn)

        self.openaiUrlTranslationLabel = QLabel("OpenAI API URL")
        self.openaiUrlTranslationInput = QLineEdit()
        
        self.openaiModelTranslationLabel = QLabel("OpenAI Model")
        self.openaiModelTranslationInput = QLineEdit()
        
        self.openaiKeyTranslationLabel = QLabel("OpenAI API Key")
        self.openaiKeyTranslationInput = QLineEdit()
        self.openaiKeyTranslationInput.setEchoMode(QLineEdit.EchoMode.Password)

        translation_layout.addWidget(self.translation_preset_btn)
        translation_layout.addLayout(translation_preset_layout)
        translation_layout.addWidget(self.openaiUrlTranslationLabel)
        translation_layout.addWidget(self.openaiUrlTranslationInput)
        translation_layout.addWidget(self.openaiModelTranslationLabel)
        translation_layout.addWidget(self.openaiModelTranslationInput)
        translation_layout.addWidget(self.openaiKeyTranslationLabel)
        translation_layout.addWidget(self.openaiKeyTranslationInput)
        translation_layout.addStretch()
        
        translation_group_box.setLayout(translation_layout)
        
        # Add group boxes to openai layout
        openai_layout.addWidget(ocr_group_box)
        openai_layout.addWidget(translation_group_box)
        openai_layout.addStretch()

        openai2_tab = QWidget()
        openai2_layout = QVBoxLayout(openai2_tab)

        prompt_label = QLabel("OpenAI Translation Prompt")
        self.translation_prompt = QTextEdit()
        self.translation_prompt.setPlainText(settings_service.get("openai_translation_prompt"))

        openai2_layout.addWidget(prompt_label)
        openai2_layout.addWidget(self.translation_prompt)
        openai2_layout.addStretch()

        # DeepLX Settings tab
        deeplx_tab = QWidget()
        deeplx_layout = QVBoxLayout(deeplx_tab)
        
        deeplx_group_box = QGroupBox("DeepLX API")
        deeplx_group_layout = QVBoxLayout()
        
        self.deeplxUrlLabel = QLabel("DeepLX API URL")
        self.deeplxUrlInput = QLineEdit()
        
        deeplx_group_layout.addWidget(self.deeplxUrlLabel)
        deeplx_group_layout.addWidget(self.deeplxUrlInput)
        deeplx_group_layout.addStretch()
        
        deeplx_group_box.setLayout(deeplx_group_layout)
        deeplx_layout.addWidget(deeplx_group_box)
        deeplx_layout.addStretch()
        
        # Add tabs to tab widget
        settings_tabs.addTab(general_tab, "General")
        settings_tabs.addTab(openai_tab, "OpenAI Api")
        settings_tabs.addTab(openai2_tab, "OpenAI Api 2")
        settings_tabs.addTab(deeplx_tab, "DeepLX")

        layout.addWidget(settings_tabs)
        
        # Save button for all settings
        saveSettingsBtn = QPushButton("Save Settings")
        saveSettingsBtn.clicked.connect(self.save_settings)
        layout.addWidget(saveSettingsBtn)
        
        layout.addStretch()

    def create_translation_preset(self):
        name, ok = QInputDialog.getText(self, "Create Translation Preset", "Enter preset name:")

        if ok and name.strip():
            name = name.strip()
            settings_service.set("translation_presets."+name,
                {"url": "", "model": "", "key": ""})

            self.translation_preset_btn.addItem(name)
            self.translation_preset_btn.setCurrentIndex(self.translation_preset_btn.count() - 1)

            # Register preset engines and update engine buttons
            self.TranslationManager.registerPresetEngines()
            self.translateEngineBtn.clear()
            self.translateEngineBtn.addItems(self.TranslationManager.available_engines())

    def create_ocr_preset(self):
        name, ok = QInputDialog.getText(self, "Create OCR Preset", "Enter preset name:")

        if ok and name.strip():
            name = name.strip()
            settings_service.set("ocr_presets."+name,
                {"url": "", "model": "", "key": ""})

            self.ocr_preset_btn.addItem(name)
            self.ocr_preset_btn.setCurrentIndex(self.ocr_preset_btn.count() - 1)

            # Register preset engines and update engine buttons
            self.OcrManager.registerPresetEngines()
            self.ocrEngineBtn.clear()
            self.ocrEngineBtn.addItems(self.OcrManager.available_engines())

    def delete_translation_preset(self):
        current_preset = self.translation_preset_btn.currentText().strip()

        if not current_preset:
            return

        if self.translation_preset_btn.count() <= 1:
            return

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            'Confirm Delete',
            f'Are you sure you want to delete the preset "{current_preset}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.No:
            return

        # Get current presets, remove the selected one, and save back
        current_presets = settings_service.get("translation_presets") or {}
        if current_preset in current_presets:
            del current_presets[current_preset]
            settings_service.set("translation_presets", current_presets)

        # Remove from combo box
        current_index = self.translation_preset_btn.currentIndex()
        self.translation_preset_btn.removeItem(current_index)

        # Select the first available preset
        if self.translation_preset_btn.count() > 0:
            self.translation_preset_btn.setCurrentIndex(0)

        # Register preset engines and update engine buttons
        self.TranslationManager.registerPresetEngines()
        self.translateEngineBtn.clear()
        self.translateEngineBtn.addItems(self.TranslationManager.available_engines())

    def delete_ocr_preset(self):
        current_preset = self.ocr_preset_btn.currentText().strip()

        if not current_preset:
            return

        if self.ocr_preset_btn.count() <= 1:
            return

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            'Confirm Delete',
            f'Are you sure you want to delete the OCR preset "{current_preset}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.No:
            return

        # Get current presets, remove the selected one, and save back
        current_presets = settings_service.get("ocr_presets") or {}
        if current_preset in current_presets:
            del current_presets[current_preset]
            settings_service.set("ocr_presets", current_presets)

        # Remove from combo box
        current_index = self.ocr_preset_btn.currentIndex()
        self.ocr_preset_btn.removeItem(current_index)

        # Select the first available preset
        if self.ocr_preset_btn.count() > 0:
            self.ocr_preset_btn.setCurrentIndex(0)

        # Register preset engines and update engine buttons
        self.OcrManager.registerPresetEngines()
        self.ocrEngineBtn.clear()
        self.ocrEngineBtn.addItems(self.OcrManager.available_engines())

    def load_settings(self):
        """Load settings and initialize UI elements"""
        # Load OCR engine setting
        current_engine = settings_service.get("ocr_engine")
        index = self.ocrEngineBtn.findText(current_engine)
        if index >= 0:
            self.ocrEngineBtn.setCurrentIndex(index)
        
        # Load OCR language setting
        ocr_language = settings_service.get("source_lang")
        self.ocrLanguageInput.setText(ocr_language)
        
        # Load translation input language setting
        translation_input_language = settings_service.get("translation_source_lang")
        self.translationInputLanguageInput.setText(translation_input_language)
        
        # Load translation engine setting
        current_translation_engine = settings_service.get("translation_engine") # engines
        self.translateEngineBtn.setCheckedItems(current_translation_engine)
        
        # Load translation output language setting
        translation_language = settings_service.get("translation_target_lang")
        self.translationLanguageInput.setText(translation_language)
        
        # Load hotkey settings
        hotkeys = settings_service.get("hotkeys")
        for action, hotkey in hotkeys.items():
            if action in self.hotkey_inputs:
                self.hotkey_inputs[action].setText(hotkey)

        self.loadOpenaiSettings()
        self.loadDeepLXSettings()
    
    def loadDeepLXSettings(self):
        deeplx_api_url = settings_service.get("deeplx_api_url")
        self.deeplxUrlInput.setText(deeplx_api_url)     
    
    def loadOpenaiSettings(self):
        current_preset_translation = self.translation_preset_btn.currentText().strip()
        openai_api_translation_url = settings_service.get("translation_presets."+current_preset_translation+".url")
        self.openaiUrlTranslationInput.setText(openai_api_translation_url)
        
        openai_api_translation_model = settings_service.get("translation_presets."+current_preset_translation+".model")
        self.openaiModelTranslationInput.setText(openai_api_translation_model)

        openai_api_translation_key = settings_service.get("translation_presets."+current_preset_translation+".key")
        self.openaiKeyTranslationInput.setText(openai_api_translation_key)
        
        current_preset_ocr = self.ocr_preset_btn.currentText().strip()
        openai_api_ocr_url = settings_service.get("ocr_presets."+current_preset_ocr+".url")
        self.openaiUrlOcrInput.setText(openai_api_ocr_url)
        
        openai_api_ocr_model = settings_service.get("ocr_presets."+current_preset_ocr+".model")
        self.openaiModelOcrInput.setText(openai_api_ocr_model)

        openai_api_ocr_key = settings_service.get("ocr_presets."+current_preset_ocr+".key")
        self.openaiKeyOcrInput.setText(openai_api_ocr_key)
        
    def save_language_settings(self):
        """Save the language settings"""
        # Save OCR language setting
        ocr_language = self.ocrLanguageInput.text().strip()
        settings_service.set("source_lang", ocr_language)
        
        # Save translation input language setting
        translation_input_language = self.translationInputLanguageInput.text().strip()
        settings_service.set("translation_source_lang", translation_input_language)
        
        # Save translation output language setting
        translation_language = self.translationLanguageInput.text().strip()
        settings_service.set("translation_target_lang", translation_language)

    def populate_hotkey_settings(self):
        """Populate the hotkey settings form with current hotkeys"""
        # Add hotkey inputs for each action
        hotkeys = self.hotkey_manager.get_hotkeys()
        for action, hotkey in hotkeys.items():
            label = QLabel(self.format_action_name(action))
            input_field = QLineEdit(hotkey)
            input_field.setObjectName(f"hotkey_{action}")
            self.hotkey_inputs[action] = input_field
            self.hotkeyForm.addRow(label, input_field)
    
    def format_action_name(self, action):
        """Format action name for display"""
        return action.replace('_', ' ').title()
    
    def save_hotkeys(self):
        """Save the updated hotkey configuration"""
        # new_hotkeys = {}
        for action, input_field in self.hotkey_inputs.items():
            hotkey = input_field.text().strip()
            if hotkey:  # Only add non-empty hotkeys
                # new_hotkeys[hotkey] = action
                self.hotkey_manager.update_hotkey(hotkey, action)

        # Save hotkey settings
        hotkeys = {}
        for action, input_field in self.hotkey_inputs.items():
            hotkeys[action] = input_field.text().strip()
        settings_service.set("hotkeys", hotkeys)
        
        # Restart hotkey listening
        self.hotkey_manager.restart_listening()
    
    def save_engines(self):
        ocr_engine = self.ocrEngineBtn.currentText().strip()
        settings_service.set("ocr_engine", ocr_engine)

        translation_engines = self.translateEngineBtn.checkedItemsText()
        settings_service.set("translation_engine", translation_engines)

    def save_openai(self):
        current_preset_translation = self.translation_preset_btn.currentText().strip()

        # Save translation settings
        openai_api_translation_url = self.openaiUrlTranslationInput.text().strip()
        settings_service.set("translation_presets."+current_preset_translation+".url", openai_api_translation_url)

        openai_api_translation_model = self.openaiModelTranslationInput.text().strip()
        settings_service.set("translation_presets."+current_preset_translation+".model", openai_api_translation_model)

        openai_api_translation_key = self.openaiKeyTranslationInput.text().strip()
        settings_service.set("translation_presets."+current_preset_translation+".key", openai_api_translation_key)
        
        current_preset_ocr = self.ocr_preset_btn.currentText().strip()
        # Save OCR settings
        openai_api_ocr_url = self.openaiUrlOcrInput.text().strip()
        settings_service.set("ocr_presets."+current_preset_ocr+".url", openai_api_ocr_url)

        openai_api_ocr_model = self.openaiModelOcrInput.text().strip()
        settings_service.set("ocr_presets."+current_preset_ocr+".model", openai_api_ocr_model)

        openai_api_ocr_key = self.openaiKeyOcrInput.text().strip()
        settings_service.set("ocr_presets."+current_preset_ocr+".key", openai_api_ocr_key)
    
    def save_deeplx(self):
        deeplx_api_url = self.deeplxUrlInput.text().strip()
        settings_service.set("deeplx_api_url", deeplx_api_url)
    
    def save_settings(self):
        """Save all settings"""
        self.save_engines()
        self.save_language_settings()
        self.save_hotkeys()
        self.save_openai()
        self.save_deeplx()
        # Save translation prompt
        settings_service.set("openai_translation_prompt", self.translation_prompt.toPlainText())
    
    def changeOcrEngine(self, name, OcrManager):
        OcrManager.swap_engine(name)
    
    def changeTranslationEngine(self, names, TranslationManager):
        TranslationManager.update_active_engines(names)
    
    def start_change_ocr_engine(self, name):
        self.ocrEngineBtn.setEnabled(False)
        worker = Worker(fn=self.changeOcrEngine, OcrManager=self.OcrManager, name=name)
        worker.signals.finished.connect(self.on_swap_finished)

        self.threadpool.start(worker)

    def start_change_translate_engine(self, names):
        self.translateEngineBtn.setEnabled(False)
        worker = Worker(fn=self.changeTranslationEngine, TranslationManager=self.TranslationManager, names=names)
        worker.signals.finished.connect(self.on_translation_swap_finished)

        self.threadpool.start(worker)

    def on_swap_finished(self):
        print("Engine swap finished.")
        self.ocrEngineBtn.setEnabled(True)

    def on_translation_swap_finished(self):
        print("Translation Engine swap finished.")
        self.translateEngineBtn.setEnabled(True)