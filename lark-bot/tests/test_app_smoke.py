from __future__ import annotations

import os
import pytest

from app import build_settings, SettingsError


def test_settings_requires_app_id_and_secret(monkeypatch):
    monkeypatch.delenv("LARK_APP_ID", raising=False)
    monkeypatch.delenv("LARK_APP_SECRET", raising=False)
    with pytest.raises(SettingsError):
        build_settings()


def test_settings_defaults_intl_api_base(monkeypatch):
    monkeypatch.setenv("LARK_APP_ID", "cli_x")
    monkeypatch.setenv("LARK_APP_SECRET", "s")
    monkeypatch.setenv("LARK_TENANT_KEY", "tk")
    monkeypatch.setenv("INCIDENTFOX_TEAM_TOKEN", "tok")
    monkeypatch.setenv("INCIDENTFOX_ORG_ID", "o")
    monkeypatch.setenv("INCIDENTFOX_TEAM_ID", "t")
    monkeypatch.delenv("LARK_API_BASE", raising=False)
    s = build_settings()
    assert s.api_base == "https://open.larksuite.com"
    assert s.transport_mode in {"long_connection", "webhook", "hybrid"}


def test_settings_phase1_rejects_oauth_enabled(monkeypatch):
    monkeypatch.setenv("LARK_APP_ID", "x")
    monkeypatch.setenv("LARK_APP_SECRET", "s")
    monkeypatch.setenv("LARK_TENANT_KEY", "tk")
    monkeypatch.setenv("INCIDENTFOX_TEAM_TOKEN", "tok")
    monkeypatch.setenv("INCIDENTFOX_ORG_ID", "o")
    monkeypatch.setenv("INCIDENTFOX_TEAM_ID", "t")
    monkeypatch.setenv("LARK_OAUTH_ENABLED", "true")
    with pytest.raises(SettingsError):
        build_settings()
