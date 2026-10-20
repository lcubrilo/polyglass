import json

import pytest

from polyglass import config as config_module
from polyglass.config import CONFIG_VERSION, Config
from polyglass.hotkeys import parse


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(Config, "path", classmethod(lambda cls: path))
    return path


def test_first_load_writes_defaults(config_path):
    cfg = Config.load()
    assert config_path.exists()
    assert cfg.allow_unofficial_google is False
    assert json.loads(config_path.read_text())["config_version"] == CONFIG_VERSION


def test_old_unversioned_config_is_migrated(config_path):
    config_path.write_text(json.dumps({"hotkey_stop": "Ctrl+Alt+Shift+L", "target_lang": "sr"}))
    cfg = Config.load()
    assert cfg.hotkey_stop == "Ctrl+Alt+X"
    assert cfg.target_lang == "sr"
    assert cfg.config_version == CONFIG_VERSION


def test_unknown_keys_are_ignored_and_bad_json_falls_back(config_path):
    config_path.write_text(json.dumps({"no_such_setting": 1}))
    assert not hasattr(Config.load(), "no_such_setting")
    config_path.write_text("{not json")
    assert Config.load().source_lang == Config().source_lang


def test_deepl_key_comes_from_environment(monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "abc")
    assert config_module.deepl_key() == "abc"


@pytest.mark.parametrize(
    "combo, expected",
    [
        ("Ctrl+Alt+L", (0x4000 | 0x2 | 0x1, ord("L"))),
        ("Alt+Shift+F5", (0x4000 | 0x1 | 0x4, 0x74)),
        ("ctrl+alt+x", (0x4000 | 0x2 | 0x1, ord("X"))),
    ],
)
def test_hotkey_parsing(combo, expected):
    assert parse(combo) == expected


def test_hotkey_parsing_rejects_nonsense():
    with pytest.raises(ValueError):
        parse("Hyper+L")
