"""API keys: an environment variable wins; otherwise the key saved in Windows Credential Manager.
Keys are never written to Polyglass's own files or logs."""

import logging
import os

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

log = logging.getLogger(__name__)

SERVICE = "Polyglass"
ENV_VARS = {"deepl": "DEEPL_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def get_key(name: str) -> str | None:
    value = os.environ.get(ENV_VARS[name])
    if value:
        return value
    try:
        return keyring.get_password(SERVICE, name) or None
    except KeyringError as exc:
        log.warning("Could not read the %s key from Credential Manager: %s", name, exc)
        return None


def key_source(name: str) -> str | None:
    """'environment', 'credential manager' or None, for showing where a key comes from."""
    if os.environ.get(ENV_VARS[name]):
        return "environment"
    try:
        return "credential manager" if keyring.get_password(SERVICE, name) else None
    except KeyringError:
        return None


def save_key(name: str, value: str) -> None:
    if value:
        keyring.set_password(SERVICE, name, value)
        return
    try:
        keyring.delete_password(SERVICE, name)
    except PasswordDeleteError:
        pass
