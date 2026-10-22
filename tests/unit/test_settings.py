from pathlib import Path

import pytest

from cm_agents.settings import SettingsError, load_settings, parse_env_text

SECRET = "super-secret-value"
URL = "https://dev123.service-now.com"


def _complete(**overrides: str) -> dict[str, str]:
    values = {
        "SN_INSTANCE_URL": URL,
        "SN_ADMIN_USER": "admin",
        "SN_ADMIN_PASSWORD": SECRET,
        "SN_AGENT_USER": "syn.svc.change_agents",
        "SN_AGENT_PASSWORD": "agent-secret",
        "XAI_API_KEY": "xai-secret",
        "XAI_MODEL": "grok-test",
    }
    values.update(overrides)
    return values


def _write(path: Path, values: dict[str, str] | None = None, *, raw: bytes | None = None) -> None:
    if raw is not None:
        path.write_bytes(raw)
        return
    assert values is not None
    text = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    path.write_text(text, encoding="utf-8")


def test_strips_utf8_bom(tmp_path: Path) -> None:
    body = "\n".join(f"{key}={value}" for key, value in _complete().items()) + "\n"
    env = tmp_path / ".env"
    env.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    settings = load_settings(env)
    assert settings.sn_instance_url == URL


def test_handles_crlf(tmp_path: Path) -> None:
    lines = [f"{key}={value}" for key, value in _complete().items()]
    env = tmp_path / ".env"
    env.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    settings = load_settings(env)
    assert settings.sn_agent_user == "syn.svc.change_agents"
    assert settings.xai_model == "grok-test"


def test_skips_blank_lines(tmp_path: Path) -> None:
    lines = ["", "   ", * [f"{key}={value}" for key, value in _complete().items()], ""]
    env = tmp_path / ".env"
    env.write_text("\n".join(lines), encoding="utf-8")
    assert load_settings(env).sn_admin_user == "admin"


def test_skips_hash_comments(tmp_path: Path) -> None:
    comment = f"# SN_ADMIN_PASSWORD={SECRET}-comment"
    body = "\n".join([comment, *[f"{key}={value}" for key, value in _complete().items()]])
    env = tmp_path / ".env"
    env.write_text(body, encoding="utf-8")
    settings = load_settings(env)
    assert settings.sn_admin_password == SECRET


def test_trims_whitespace(tmp_path: Path) -> None:
    values = _complete(SN_ADMIN_USER="admin")
    lines = [f"  {key}   =   {value}  " for key, value in values.items()]
    env = tmp_path / ".env"
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.sn_admin_user == "admin"
    assert settings.sn_instance_url == URL


def test_strips_one_pair_of_double_quotes(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, _complete(SN_ADMIN_USER='"admin"', XAI_MODEL='"grok test"'))
    settings = load_settings(env)
    assert settings.sn_admin_user == "admin"
    assert settings.xai_model == "grok test"


def test_strips_one_pair_of_single_quotes(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, _complete(SN_AGENT_USER="'syn.svc.change_agents'"))
    assert load_settings(env).sn_agent_user == "syn.svc.change_agents"


def test_strips_only_one_matching_pair() -> None:
    parsed = parse_env_text('SN_ADMIN_USER="\'admin\'"\n')
    assert parsed["SN_ADMIN_USER"] == "'admin'"


def test_leaves_mismatched_quotes() -> None:
    parsed = parse_env_text('SN_ADMIN_USER="admin\n')
    assert parsed["SN_ADMIN_USER"] == '"admin'


def test_trims_inside_quotes(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, _complete(XAI_MODEL='" grok-test "'))
    assert load_settings(env).xai_model == "grok-test"


def test_missing_key_names_the_key_and_not_the_value(tmp_path: Path) -> None:
    values = _complete()
    del values["SN_INSTANCE_URL"]
    env = tmp_path / ".env"
    _write(env, values)
    with pytest.raises(SettingsError) as exc:
        load_settings(env)
    message = str(exc.value)
    assert "SN_INSTANCE_URL" in message
    assert SECRET not in message
    assert "xai-secret" not in message


def test_empty_key_names_the_key_and_not_the_value(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, _complete(SN_ADMIN_PASSWORD=""))
    with pytest.raises(SettingsError) as exc:
        load_settings(env)
    message = str(exc.value)
    assert "SN_ADMIN_PASSWORD" in message
    assert SECRET not in message
    assert "xai-secret" not in message


def test_empty_quoted_key_names_the_key(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, _complete(XAI_API_KEY='""'))
    with pytest.raises(SettingsError) as exc:
        load_settings(env)
    message = str(exc.value)
    assert "XAI_API_KEY" in message
    assert SECRET not in message


def test_missing_file_names_required_keys(tmp_path: Path) -> None:
    with pytest.raises(SettingsError) as exc:
        load_settings(tmp_path / "absent.env")
    message = str(exc.value)
    assert "SN_AGENT_PASSWORD" in message
    assert "XAI_API_KEY" in message


def test_guard_accepts_pdi_url(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, _complete(SN_INSTANCE_URL="https://dev123456.service-now.com"))
    assert load_settings(env).sn_instance_url == "https://dev123456.service-now.com"


@pytest.mark.parametrize(
    "url",
    [
        "http://dev123.service-now.com",
        "https://dev.service-now.com",
        "https://example.service-now.com",
        "https://dev123.service-now.com/",
        "https://dev123.service-now.com/api",
        "https://dev123.service-now.com.evil.com",
        "https://DEV123.service-now.com",
    ],
)
def test_guard_rejects_non_pdi_url_without_echoing_it(tmp_path: Path, url: str) -> None:
    env = tmp_path / ".env"
    _write(env, _complete(SN_INSTANCE_URL=url))
    with pytest.raises(SettingsError) as exc:
        load_settings(env)
    message = str(exc.value)
    assert "SN_INSTANCE_URL" in message
    assert url not in message
    assert SECRET not in message


def test_repr_hides_secrets(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, _complete())
    settings = load_settings(env)
    assert SECRET not in repr(settings)
    assert "xai-secret" not in repr(settings)
