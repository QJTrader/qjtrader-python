import os

import pytest

from qjtrader import Client
from qjtrader.errors import QJError


def _write_credentials(path, text):
    path.write_text(text, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def test_client_from_env_file_loads_machine_credentials_without_mutating_environment(
        tmp_path, monkeypatch):
    monkeypatch.delenv("QJ_CLIENT_ID", raising=False)
    monkeypatch.delenv("QJ_CLIENT_SECRET", raising=False)
    credentials = tmp_path / "qj.env"
    _write_credentials(credentials, "QJ_CLIENT_ID=m3-shadow\nQJ_CLIENT_SECRET='secret value'\n")

    client = Client.from_env_file(credentials)

    assert client._client_id == "m3-shadow"
    assert client._client_secret == "secret value"
    assert "QJ_CLIENT_ID" not in os.environ
    assert "QJ_CLIENT_SECRET" not in os.environ


def test_client_from_env_file_rejects_missing_secret(tmp_path):
    credentials = tmp_path / "qj.env"
    _write_credentials(credentials, "QJ_CLIENT_ID=m3-shadow\n")

    with pytest.raises(QJError, match="QJ_CLIENT_SECRET"):
        Client.from_env_file(credentials)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file mode check")
def test_client_from_env_file_rejects_group_or_world_readable_secret(tmp_path):
    credentials = tmp_path / "qj.env"
    credentials.write_text("QJ_CLIENT_ID=x\nQJ_CLIENT_SECRET=y\n", encoding="utf-8")
    credentials.chmod(0o644)

    with pytest.raises(QJError, match="chmod 600"):
        Client.from_env_file(credentials)
