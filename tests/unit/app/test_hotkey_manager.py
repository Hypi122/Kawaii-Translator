import pytest
from App.hotkey_manager import HotkeyManager

@pytest.fixture
def mock_settings(mocker):
    mock = mocker.patch('App.hotkey_manager.settings_service')
    mock.get.return_value = {
        "ocr_capture": "<alt>+q",
        "only_ocr": "<alt>+w",
        "cancel_selection": "<esc>"
    }
    return mock

@pytest.fixture
def mock_keyboard(mocker):
    mock_listener = mocker.MagicMock()
    mock_global_hotkeys = mocker.patch("App.hotkey_manager.keyboard.GlobalHotKeys", return_value=mock_listener)
    return mock_global_hotkeys, mock_listener

@pytest.fixture
def hotkey_manager(mock_settings, mock_keyboard):
    manager = HotkeyManager()
    return manager

class TestHotkeyManagerInit:
    def test_init_loads_settings(self, mock_keyboard, mock_settings):
        manager = HotkeyManager()
        mock_settings.get.assert_called_with("hotkeys")

    def test_init_starts_listener(self, mock_keyboard, mock_settings):
        mock_global_hotkeys, mock_listener = mock_keyboard
        manager = HotkeyManager()
        mock_listener.start.assert_called_once()

class TestHotkeyManagerGetHotkeys:
    def test_get_hotkeys_returns_copy(self, hotkey_manager):
        hotkeys = hotkey_manager.get_hotkeys()
        assert hotkeys == {
            "ocr_capture": "<alt>+q",
            "only_ocr": "<alt>+w",
            "cancel_selection": "<esc>"
        }
        # Verify it's a copy
        hotkeys["new_action"] = "<ctrl>+n"
        assert "new_action" not in hotkey_manager.get_hotkeys()

class TestHotkeyManagerUpdateHotkey:
    def test_update_hotkey_changes_action(self, hotkey_manager):
        hotkey_manager.update_hotkey("<ctrl>+q", "ocr_capture")
        assert hotkey_manager.get_hotkeys()["ocr_capture"] == "<ctrl>+q"

    def test_update_hotkey_adds_new_action(self, hotkey_manager):
        hotkey_manager.update_hotkey("<ctrl>+n", "new_action")
        assert hotkey_manager.get_hotkeys()["new_action"] == "<ctrl>+n"

class TestHotkeyManagerListening:
    def test_stop_listening_stops_all_listeners(self, hotkey_manager, mock_keyboard):
        mock_global_hotkeys, mock_listener = mock_keyboard
        assert len(hotkey_manager.listeners) > 0
        
        hotkey_manager.stop_listening()
        
        mock_listener.stop.assert_called()
        assert len(hotkey_manager.listeners) == 0

    def test_restart_listening_stops_and_starts_listeners(self, hotkey_manager, mock_keyboard):
        mock_global_hotkeys, mock_listener = mock_keyboard
        initial_call_count = mock_listener.start.call_count
        initial_listener_count = len(hotkey_manager.listeners)

        hotkey_manager.restart_listening()

        assert mock_listener.start.call_count > initial_call_count
        mock_listener.stop.assert_called()
        assert len(hotkey_manager.listeners) == initial_listener_count

class TestHotkeyManagerSignals:
    def test_hotkey_triggered_signal_emitted(self, qtbot, hotkey_manager, mock_keyboard):
        mock_global_hotkeys, mock_listener = mock_keyboard
        
        # call_args[0] are positional args, [0] is the first arg 
        # passed to keyboard.GlobalHotKeys (the dictionary)
        # {
        #     "<alt>+q": function_to_call_for_capture,
        #     "<esc>": function_to_call_for_cancel,
        #     ...
        # }
        hotkey_mapping = mock_global_hotkeys.call_args[0][0]
        with qtbot.waitSignal(hotkey_manager.hotkey_triggered) as blocker:
            # trigger the lambda function
            hotkey_mapping["<alt>+q"]()
        
        assert blocker.args[0] == "ocr_capture"