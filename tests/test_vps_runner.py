import base64
import importlib.util
import json
import logging
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("vps_runner", ROOT / "deploy/run.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def jwt(exp, scope=128):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp, "s": scope}).encode()).decode().rstrip("=")
    return f"test.{payload}.test"


def test_expired_or_read_only_wb_key_cannot_publish():
    env = {"OPENAI_API_KEY": "test", "WB_TOKEN": jwt(time.time() - 1)}
    assert any("истёк" in e for e in runner.validate(env, "wb", True))
    env["WB_TOKEN"] = jwt(time.time() + 1000, 128 | (1 << 30))
    assert any("только чтение" in e for e in runner.validate(env, "wb", True))
    assert runner.validate(env, "wb", False) == []


def test_secret_filter_removes_full_key_and_truncated_key():
    secret = "sk-test-very-private-value"
    log = logging.LogRecord("test", 40, "", 0, "invalid key %s / sk-test-truncated", (secret,), None)
    assert runner.RedactSecrets({"OPENAI_API_KEY": secret}).filter(log)
    assert secret not in log.getMessage()
    assert "sk-test" not in log.getMessage()


def command(tmp_path, *args):
    secret = tmp_path / "keys.env"
    secret.write_text("OPENAI_API_KEY=test\nOZON_CLIENT_ID=test\nOZON_API_KEY=test\n")
    secret.chmod(0o600)
    state = tmp_path / "state"
    result = subprocess.run([
        sys.executable, str(ROOT / "deploy/run.py"), "ozon",
        "--env-file", str(secret), "--state-dir", str(state), *args,
    ], capture_output=True, text=True, timeout=10)
    return result, state


def test_check_does_not_create_state_or_call_apis(tmp_path):
    result, state = command(tmp_path, "--check")
    assert result.returncode == 0, result.stderr
    assert "сеть и публикация не проверялись" in result.stdout
    assert not state.exists()


def test_publish_requires_separate_activation_marker(tmp_path):
    result, state = command(tmp_path, "--publish")
    assert result.returncode == 2
    assert "Публикация не включена" in result.stderr
    assert not state.exists()


def test_unsafe_dry_run_typo_is_rejected():
    errors = runner.validate({"OPENAI_API_KEY": "test", "OZON_CLIENT_ID": "test",
                             "OZON_API_KEY": "test", "DRY_RUN": "true"}, "ozon", False)
    assert errors == ["DRY_RUN должен быть 0 или 1"]
