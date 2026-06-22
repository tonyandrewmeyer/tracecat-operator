# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the tracecat workload-interaction module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import tracecat


def _mock_response(body: bytes | str = b'{"status": "ok"}', status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body if isinstance(body, bytes) else body.encode()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_health_check_ok() -> None:
    with patch("tracecat.urllib.request.urlopen", return_value=_mock_response()):
        assert tracecat.health_check(MagicMock()) is True


def test_health_check_failure() -> None:
    with patch("tracecat.urllib.request.urlopen", side_effect=OSError("conn refused")):
        assert tracecat.health_check(MagicMock()) is False


def test_health_check_wrong_status_field() -> None:
    with patch(
        "tracecat.urllib.request.urlopen",
        return_value=_mock_response(b'{"status": "degraded"}'),
    ):
        assert tracecat.health_check(MagicMock()) is False


def test_get_version_present() -> None:
    with patch(
        "tracecat.urllib.request.urlopen",
        return_value=_mock_response(b'{"version": "1.0.0-beta.49"}'),
    ):
        assert tracecat.get_version(MagicMock()) == "1.0.0-beta.49"


def test_get_version_absent() -> None:
    with patch(
        "tracecat.urllib.request.urlopen",
        return_value=_mock_response(b'{"status": "ok"}'),
    ):
        assert tracecat.get_version(MagicMock()) is None


def test_get_version_error_returns_none() -> None:
    with patch("tracecat.urllib.request.urlopen", side_effect=OSError("nope")):
        assert tracecat.get_version(MagicMock()) is None


def test_api_get_empty_body() -> None:
    resp = _mock_response(b"")
    with patch("tracecat.urllib.request.urlopen", return_value=resp):
        assert tracecat._api_get(MagicMock(), "/x") is None


def test_api_get_non_json_body() -> None:
    with patch(
        "tracecat.urllib.request.urlopen",
        return_value=_mock_response(b"plain text"),
    ):
        assert tracecat._api_get(MagicMock(), "/x") == "plain text"


def test_make_db_uri() -> None:
    uri = tracecat.make_db_uri(host="h", port=5432, dbname="tracecat", user="u", password="p")
    assert uri == "postgresql+psycopg://u:p@h:5432/tracecat"
