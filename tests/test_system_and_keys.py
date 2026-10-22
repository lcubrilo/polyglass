import io
import json
import urllib.parse

import pytest
from keyring.errors import PasswordDeleteError

from polyglass import keys, system


@pytest.fixture
def fake_keyring(monkeypatch):
    store = {}
    monkeypatch.setattr(keys.keyring, "get_password", lambda service, name: store.get((service, name)))
    monkeypatch.setattr(
        keys.keyring, "set_password", lambda service, name, value: store.__setitem__((service, name), value)
    )

    def delete(service, name):
        if (service, name) not in store:
            raise PasswordDeleteError("not found")  # what the real Credential Manager backend raises
        del store[(service, name)]

    monkeypatch.setattr(keys.keyring, "delete_password", delete)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    return store


def test_saved_key_is_used_and_environment_wins(fake_keyring, monkeypatch):
    assert keys.get_key("deepl") is None
    keys.save_key("deepl", "saved-key")
    assert keys.get_key("deepl") == "saved-key"
    assert keys.key_source("deepl") == "credential manager"
    monkeypatch.setenv("DEEPL_API_KEY", "env-key")
    assert keys.get_key("deepl") == "env-key"
    assert keys.key_source("deepl") == "environment"


def test_saving_an_empty_key_removes_it(fake_keyring):
    keys.save_key("anthropic", "k")
    keys.save_key("anthropic", "")
    keys.save_key("anthropic", "")  # removing twice is fine
    assert keys.get_key("anthropic") is None


@pytest.mark.parametrize(
    "latest, newer",
    [("v0.2.0", True), ("v0.1.0", False), ("v0.0.9", False), ("v0.1.10", True), ("v1.0.0-beta", True)],
)
def test_update_check_compares_versions(monkeypatch, latest, newer):
    monkeypatch.setattr(system, "app_version", lambda: "0.1.0")
    body = json.dumps({"tag_name": latest, "html_url": "https://example.test/release"}).encode()
    monkeypatch.setattr(system.urllib.request, "urlopen", lambda request, timeout: io.BytesIO(body))
    result = system.newer_release()
    assert (result is not None) == newer
    if newer:
        assert result == (latest.lstrip("v"), "https://example.test/release")


def test_dev_builds_never_report_updates(monkeypatch):
    monkeypatch.setattr(system, "app_version", lambda: "dev")
    assert system.newer_release() is None


def test_bug_reports_are_prefilled_and_limited_per_day(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "polyglass.log").write_text("line one\nline two\n", encoding="utf-8")
    monkeypatch.setattr(system, "log_dir", lambda: logs)

    url = system.bug_report_url("ValueError: boom")
    fields = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert fields["template"] == ["bug_report.yml"]
    assert "ValueError: boom" in fields["what"][0]
    assert "line two" in fields["log"][0]

    for _ in range(system.REPORTS_PER_DAY - 1):
        assert system.bug_report_url("again")
    assert system.reports_left_today() == 0
    assert system.bug_report_url("one too many") is None
