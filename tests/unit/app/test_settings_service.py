import json
from App.settings_service import SettingsService

class TestSettingsServiceLoad:
    def test_load_creates_default_when_missing(self, tmp_path):
        cfg = tmp_path / "cfg.json"
        s = SettingsService(config_path=str(cfg))
        assert cfg.exists()
        assert s.get("source_lang") == "ja"

    def test_merge_preserves_current_and_fills_defaults(self, tmp_path):
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"source_lang": "pl"}), encoding="utf-8")
        s = SettingsService(config_path=str(cfg))
        assert s.get("source_lang") == "pl"
        assert s.get("translation_target_lang") == "en"  # from defaults

class TestSettingsServiceSet:
    def test_set_edits_setting(self, tmp_path):
        cfg = tmp_path / "cfg.json"
        s = SettingsService(config_path=str(cfg))
        s.set("translation_target_lang", "pl")
        assert s.get("translation_target_lang") == "pl"

    def test_set_nested_creates_parents(self, tmp_path):
        cfg = tmp_path / "cfg.json"
        url = "http://localhost:1234/v1"
        s = SettingsService(config_path=str(cfg))
        s.set("translation_presets.myPreset.url", url)
        assert s.get("translation_presets.myPreset.url") == url

class TestSettingsServiceSave:
    def test_save_settings_saves_settings_to_disk(self, tmp_path):
        cfg = tmp_path / "cfg.json"
        s = SettingsService(config_path=str(cfg))
        
        s.set("translation_target_lang", "pl")
        s.save_settings()
        
        assert cfg.exists()
        with open(cfg, 'r') as f:
            saved_data = json.load(f)
        assert saved_data["translation_target_lang"] == "pl"