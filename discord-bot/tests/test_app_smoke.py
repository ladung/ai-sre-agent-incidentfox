from __future__ import annotations

import pytest

from app import build_settings, SettingsError


def test_settings_requires_bot_token(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    with pytest.raises(SettingsError):
        build_settings()


def test_settings_requires_guild_id(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "x")
    monkeypatch.delenv("DISCORD_GUILD_ID", raising=False)
    with pytest.raises(SettingsError):
        build_settings()


def test_settings_with_all_required_present(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake")
    monkeypatch.setenv("DISCORD_APP_ID", "111")
    monkeypatch.setenv("DISCORD_GUILD_ID", "222")
    monkeypatch.setenv("INCIDENTFOX_TEAM_TOKEN", "tok")
    monkeypatch.setenv("INCIDENTFOX_ORG_ID", "o")
    monkeypatch.setenv("INCIDENTFOX_TEAM_ID", "t")
    s = build_settings()
    assert s.bot_token == "fake"
    assert s.guild_id == 222
    assert s.org_id == "o"


def test_settings_rejects_non_integer_guild_id(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake")
    monkeypatch.setenv("DISCORD_APP_ID", "111")
    monkeypatch.setenv("DISCORD_GUILD_ID", "not-a-number")
    monkeypatch.setenv("INCIDENTFOX_TEAM_TOKEN", "tok")
    monkeypatch.setenv("INCIDENTFOX_ORG_ID", "o")
    monkeypatch.setenv("INCIDENTFOX_TEAM_ID", "t")
    with pytest.raises(SettingsError):
        build_settings()
