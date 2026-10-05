"""Проверки ввода ключей только с вымышленными значениями и подставным API."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from dotenv import dotenv_values
import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
sys.path.insert(0, str(DEPLOY))
SPEC = importlib.util.spec_from_file_location("configure_marketplace", DEPLOY / "configure_marketplace.py")
wizard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wizard)


def test_saving_marketplace_preserves_other_keys_and_protects_file(tmp_path, monkeypatch):
    path = tmp_path / "keys.env"
    path.write_text("# Existing config\nOPENAI_API_KEY='fake-private'\nWB_TOKEN='fake-wb'\nMAX_COUNT=1\n")
    monkeypatch.setattr(wizard.os, "chown", lambda *args: None)
    monkeypatch.setattr(wizard.grp, "getgrnam", lambda _: SimpleNamespace(gr_gid=123))
    wizard.save(path, {"OZON_CLIENT_ID": "123", "OZON_API_KEY": "fake-'ozon"})
    assert dotenv_values(path) == {
        "OPENAI_API_KEY": "fake-private", "WB_TOKEN": "fake-wb", "MAX_COUNT": "1",
        "OZON_CLIENT_ID": "123", "OZON_API_KEY": "fake-'ozon",
    }
    assert path.stat().st_mode & 0o777 == 0o640
    assert path.read_text().startswith("# Existing config")
    assert list(tmp_path.iterdir()) == [path]


def test_failed_replacement_keeps_original_file(tmp_path, monkeypatch):
    path = tmp_path / "keys.env"
    original = "OPENAI_API_KEY=fake-private\n"
    path.write_text(original)
    monkeypatch.setattr(wizard.os, "chown", Mock(side_effect=PermissionError))
    monkeypatch.setattr(wizard.grp, "getgrnam", lambda _: SimpleNamespace(gr_gid=123))
    with pytest.raises(PermissionError):
        wizard.save(path, {"WB_TOKEN": "fake-wb"})
    assert path.read_text() == original
    assert list(tmp_path.iterdir()) == [path]


def test_probe_failure_does_not_include_response_secrets(monkeypatch):
    response = Mock(status_code=401, text="bad key: fake-private")
    post = Mock(return_value=response)
    monkeypatch.setattr(wizard.requests, "post", post)
    with pytest.raises(ValueError, match="HTTP 401") as error:
        wizard.probe("ozon", {"OZON_CLIENT_ID": "123", "OZON_API_KEY": "fake-private"})
    assert "fake-private" not in str(error.value)
    assert post.call_args.args[0].endswith("/v1/review/list")


def test_invalid_header_exception_does_not_echo_entered_key(tmp_path, monkeypatch, capsys):
    path = tmp_path / "keys.env"
    original = "OPENAI_API_KEY=fake-openai\n"
    path.write_text(original)
    secret = "fake-private-first\nfake-private-second"
    monkeypatch.setattr(sys, "argv", ["configure", "ozon", "--env-file", str(path)])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "123")
    monkeypatch.setattr(wizard.getpass, "getpass", lambda _: secret)
    # Настоящая валидация requests, без отправки в сеть.
    def prepare_only(*args, **kwargs):
        return wizard.requests.Request("POST", args[0], headers=kwargs["headers"]).prepare()
    monkeypatch.setattr(wizard.requests, "post", prepare_only)
    assert wizard.main() == 1
    output = capsys.readouterr()
    assert output.err.strip() == "InvalidHeader"
    assert "fake-private" not in output.out + output.err
    assert path.read_text() == original


@pytest.mark.parametrize(("message", "hint"), [
    ("Seller must have premium subscription", "ограничение подписки"),
    ("Request IP is not in allowlist", "по IP-адресу"),
    ("Invalid Api-Key or Client-Id", "Client ID и ключ одного кабинета"),
    ("Not enough permissions for this method", "права доступа"),
    ("Access denied", "не уточнил причину"),
])
def test_ozon_error_classification_never_prints_server_text(message, hint):
    response = Mock()
    response.json.return_value = {"code": 7, "message": message + " fake-private-key"}
    result = wizard.ozon_error_hint(response, {"OZON_API_KEY": "fake-private-key"})
    assert hint in result
    assert "Код ошибки Ozon: 7" in result
    assert "fake-private" not in result
    assert message not in result


def test_ozon_html_error_does_not_get_misdiagnosed_as_subscription():
    response = Mock(text="secret-header: fake-private-key")
    response.json.side_effect = ValueError("bad JSON with fake-private-key")
    result = wizard.ozon_error_hint(response, {})
    assert "не JSON" in result
    assert "подписка по этому ответу не определена" in result
    assert "fake-private" not in result


def test_ozon_error_ignores_nonstring_message_and_secret_like_error_code():
    response = Mock()
    response.json.return_value = {"code": "fake-private-key", "message": {"api-key": "fake-private-key"}}
    result = wizard.ozon_error_hint(response, {})
    assert "не уточнил причину" in result
    assert "fake-private" not in result
