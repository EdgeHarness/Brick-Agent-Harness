"""Operator-owned connector secrets stored outside the repository."""
import hashlib
import json
import re

from .errors import ConnectorUnavailable


_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def account_fingerprint(identity):
    if not isinstance(identity, str) or not identity:
        raise ValueError("account identity must be a nonempty string")
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class KeyringSecretStore:
    """Small key/value facade over the platform credential vault."""

    def __init__(self, namespace="brick-agent-harness"):
        try:
            import keyring
        except ImportError as exc:
            raise ConnectorUnavailable(
                "connector credentials require the optional keyring dependency"
            ) from exc
        backend = keyring.get_keyring()
        if getattr(backend, "priority", 0) <= 0:
            raise ConnectorUnavailable("no secure OS keyring backend is available")
        self._keyring = keyring
        self.namespace = namespace

    def _labels(self, provider, account, key):
        for value, label in ((provider, "provider"), (account, "account"), (key, "key")):
            if not isinstance(value, str) or not _NAME.fullmatch(value):
                raise ValueError(f"invalid credential {label}")
        return f"{self.namespace}:{provider}:{account}", key

    def get(self, provider, account, key):
        service, username = self._labels(provider, account, key)
        try:
            return self._keyring.get_password(service, username)
        except Exception as exc:
            raise ConnectorUnavailable("OS keyring read failed") from exc

    def set(self, provider, account, key, value):
        if not isinstance(value, str) or not value:
            raise ValueError("credential value must be a nonempty string")
        service, username = self._labels(provider, account, key)
        try:
            self._keyring.set_password(service, username, value)
        except Exception as exc:
            raise ConnectorUnavailable("OS keyring write failed") from exc

    def delete(self, provider, account, key):
        service, username = self._labels(provider, account, key)
        try:
            self._keyring.delete_password(service, username)
        except self._keyring.errors.PasswordDeleteError:
            return False
        except Exception as exc:
            raise ConnectorUnavailable("OS keyring delete failed") from exc
        return True

    def get_json(self, provider, account, key):
        raw = self.get(provider, account, key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise ConnectorUnavailable("stored connector credential is corrupt") from exc

    def set_json(self, provider, account, key, value):
        self.set(
            provider,
            account,
            key,
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )


class MemorySecretStore:
    """Credential-free test double; never selected by production code."""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, provider, account, key):
        return self.values.get((provider, account, key))

    def set(self, provider, account, key, value):
        self.values[(provider, account, key)] = value

    def delete(self, provider, account, key):
        return self.values.pop((provider, account, key), None) is not None

    def get_json(self, provider, account, key):
        raw = self.get(provider, account, key)
        return None if raw is None else json.loads(raw)

    def set_json(self, provider, account, key, value):
        self.set(provider, account, key, json.dumps(value, sort_keys=True))
