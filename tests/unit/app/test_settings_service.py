import json
from App.settings_service import SettingsService, default_config_path

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

class TestDefaultConfigPath:
    def test_appends_app_dir_for_plain_base(self, tmp_path, monkeypatch):
        base = tmp_path / "plain"
        monkeypatch.setattr("App.settings_service._qt_app_config_location", lambda: str(base))
        assert default_config_path() == str(base / "kawaii-translator" / "config.json")

    def test_no_duplication_when_base_ends_with_app_dir(self, tmp_path, monkeypatch):
        base = tmp_path / "kawaii-translator"
        monkeypatch.setattr("App.settings_service._qt_app_config_location", lambda: str(base))
        assert default_config_path() == str(base / "config.json")

    def test_no_duplication_with_trailing_separator(self, tmp_path, monkeypatch):
        base = str(tmp_path / "kawaii-translator") + "/"
        monkeypatch.setattr("App.settings_service._qt_app_config_location", lambda: base)
        assert default_config_path() == str(tmp_path / "kawaii-translator" / "config.json")

    def test_no_duplication_with_trailing_backslash(self, tmp_path, monkeypatch):
        base = str(tmp_path / "kawaii-translator") + "\\"
        monkeypatch.setattr("App.settings_service._qt_app_config_location", lambda: base)
        assert default_config_path() == str(tmp_path / "kawaii-translator" / "config.json")

    def test_default_creates_tree_and_file(self, tmp_path, monkeypatch):
        base = tmp_path / "nonexistent" / "subtree"
        monkeypatch.setattr("App.settings_service._qt_app_config_location", lambda: str(base))
        monkeypatch.chdir(tmp_path)
        s = SettingsService()
        cfg = tmp_path / "nonexistent" / "subtree" / "kawaii-translator" / "config.json"
        assert cfg.parent.is_dir()
        assert cfg.exists()
        assert s.get("source_lang") == "ja"

class TestLegacyMigration:
    def _patch_default_path(self, monkeypatch, tmp_path):
        base = tmp_path / "cfg_base"
        monkeypatch.setattr("App.settings_service._qt_app_config_location", lambda: str(base))
        return base

    def test_valid_legacy_is_migrated(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        original_bytes = json.dumps({"source_lang": "pl"}, indent=4).encode("utf-8")
        (tmp_path / "config.json").write_bytes(original_bytes)
        self._patch_default_path(monkeypatch, tmp_path)
        s = SettingsService()
        new_cfg = tmp_path / "cfg_base" / "kawaii-translator" / "config.json"
        assert new_cfg.exists()
        assert json.loads(new_cfg.read_text(encoding="utf-8"))["source_lang"] == "pl"
        migrated = tmp_path / "config.json.migrated"
        assert migrated.exists()
        assert migrated.read_bytes() == original_bytes
        assert not (tmp_path / "config.json").exists()
        assert s.get("source_lang") == "pl"

    def test_no_legacy_creates_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._patch_default_path(monkeypatch, tmp_path)
        s = SettingsService()
        new_cfg = tmp_path / "cfg_base" / "kawaii-translator" / "config.json"
        assert new_cfg.exists()
        assert json.loads(new_cfg.read_text(encoding="utf-8"))["source_lang"] == "ja"
        assert s.get("source_lang") == "ja"
        assert not (tmp_path / "config.json").exists()
        assert not (tmp_path / "config.json.migrated").exists()

    def test_corrupt_legacy_is_skipped(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        legacy = tmp_path / "config.json"
        legacy.write_bytes(b"{invalid json")
        self._patch_default_path(monkeypatch, tmp_path)
        s = SettingsService()
        new_cfg = tmp_path / "cfg_base" / "kawaii-translator" / "config.json"
        assert new_cfg.exists()
        assert json.loads(new_cfg.read_text(encoding="utf-8"))["source_lang"] == "ja"
        assert s.get("source_lang") == "ja"
        assert legacy.exists()
        assert legacy.read_bytes() == b"{invalid json"
        assert not (tmp_path / "config.json.migrated").exists()

    def test_non_dict_legacy_is_skipped(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        legacy = tmp_path / "config.json"
        legacy.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        self._patch_default_path(monkeypatch, tmp_path)
        s = SettingsService()
        new_cfg = tmp_path / "cfg_base" / "kawaii-translator" / "config.json"
        assert new_cfg.exists()
        assert json.loads(new_cfg.read_text(encoding="utf-8"))["source_lang"] == "ja"
        assert s.get("source_lang") == "ja"
        assert legacy.exists()
        assert legacy.read_text(encoding="utf-8") == json.dumps([1, 2, 3])
        assert not (tmp_path / "config.json.migrated").exists()
        assert not (tmp_path / "config.json.migrate-tmp").exists()
        assert not (new_cfg.parent / "config.json.migrate-tmp").exists()

    def test_new_file_wins_over_legacy(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        legacy = tmp_path / "config.json"
        legacy.write_text(json.dumps({"source_lang": "pl"}), encoding="utf-8")
        new_cfg = tmp_path / "cfg_base" / "kawaii-translator" / "config.json"
        new_cfg.parent.mkdir(parents=True)
        new_cfg.write_text(json.dumps({"source_lang": "de"}), encoding="utf-8")
        self._patch_default_path(monkeypatch, tmp_path)
        s = SettingsService()
        assert s.get("source_lang") == "de"
        assert legacy.read_text(encoding="utf-8") == json.dumps({"source_lang": "pl"})
        assert not (tmp_path / "config.json.migrated").exists()

    def test_legacy_is_directory_no_crash(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.json").mkdir()
        self._patch_default_path(monkeypatch, tmp_path)
        s = SettingsService()
        assert s.get("source_lang") == "ja"
        assert (tmp_path / "config.json").is_dir()
        assert not (tmp_path / "config.json.migrated").exists()

    def test_explicit_path_never_triggers_migration(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        legacy = tmp_path / "config.json"
        legacy.write_text(json.dumps({"source_lang": "pl"}), encoding="utf-8")
        other = tmp_path / "other"
        s = SettingsService(config_path=str(other / "cfg.json"))
        assert legacy.read_text(encoding="utf-8") == json.dumps({"source_lang": "pl"})
        assert not (tmp_path / "config.json.migrated").exists()
        assert (other / "cfg.json").exists()
        assert s.get("source_lang") == "ja"