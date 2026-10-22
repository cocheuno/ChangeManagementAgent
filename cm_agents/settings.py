"""Load connection settings from .env. Never log or persist the values."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

REQUIRED_KEYS: tuple[str, ...] = (
    "SN_INSTANCE_URL",
    "SN_ADMIN_USER",
    "SN_ADMIN_PASSWORD",
    "SN_AGENT_USER",
    "SN_AGENT_PASSWORD",
    "XAI_API_KEY",
    "XAI_MODEL",
)

# Personal Developer Instances only. The client refuses every other host.
PDI_URL_PATTERN = re.compile(r"^https://dev\d+\.service-now\.com$")

_ENV_FIELDS = {
    "SN_INSTANCE_URL": "sn_instance_url",
    "SN_ADMIN_USER": "sn_admin_user",
    "SN_ADMIN_PASSWORD": "sn_admin_password",
    "SN_AGENT_USER": "sn_agent_user",
    "SN_AGENT_PASSWORD": "sn_agent_password",
    "XAI_API_KEY": "xai_api_key",
    "XAI_MODEL": "xai_model",
}


class SettingsError(Exception):
    """A required setting is missing, empty, or not a PDI URL."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sn_instance_url: str = Field(repr=False)
    sn_admin_user: str = Field(repr=False)
    sn_admin_password: str = Field(repr=False)
    sn_agent_user: str = Field(repr=False)
    sn_agent_password: str = Field(repr=False)
    xai_api_key: str = Field(repr=False)
    xai_model: str = Field(repr=False)

    def secret_values(self) -> list[str]:
        """Values that must never appear in logs, errors, or committed files."""
        return [self.sn_admin_password, self.sn_agent_password, self.xai_api_key]


def repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd()


def parse_env_text(text: str) -> dict[str, str]:
    """Parse .env text. Last assignment wins. Inline comments are not stripped."""
    if text.startswith("\ufeff"):
        text = text[1:]
    values: dict[str, str] = {}
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SettingsError(f"Invalid .env line {line_no}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_matching_quotes(value.strip())
        if not key:
            raise SettingsError(f"Invalid .env line {line_no}: expected KEY=VALUE")
        values[key] = value
    return values


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def assert_pdi_url(url: str) -> None:
    if PDI_URL_PATTERN.fullmatch(url) is None:
        raise SettingsError("SN_INSTANCE_URL is not a Personal Developer Instance URL")


def load_settings(path: Path | None = None) -> Settings:
    env_path = path if path is not None else repo_root() / ".env"
    if not env_path.is_file():
        names = ", ".join(REQUIRED_KEYS)
        raise SettingsError(f"Missing or empty required setting: {names}")
    text = env_path.read_text(encoding="utf-8-sig")
    values = parse_env_text(text)
    missing = [key for key in REQUIRED_KEYS if values.get(key, "") == ""]
    if missing:
        raise SettingsError("Missing or empty required setting: " + ", ".join(missing))
    assert_pdi_url(values["SN_INSTANCE_URL"])
    mapped = {_ENV_FIELDS[key]: values[key] for key in REQUIRED_KEYS}
    return Settings(**mapped)


def redact_text(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "***")
    return redacted
