"""app/cli.py create-superadmin: the answers the Windows installer gives in the environment (instalador/)."""
import pytest

from app import cli


def test_superadmin_answers_from_the_environment(monkeypatch):
    monkeypatch.setenv("RMSOFT_ADMIN_NAME", "Técnico RM SOFT")
    monkeypatch.setenv("RMSOFT_ADMIN_PHONE", "+244 923 000 999")
    monkeypatch.setenv("RMSOFT_ADMIN_PASSWORD", "Segredo@2026")
    assert cli._given_superadmin() == ("Técnico RM SOFT", "+244923000999", "Segredo@2026")


def test_without_the_environment_the_questions_are_asked(monkeypatch):
    for name in ("RMSOFT_ADMIN_NAME", "RMSOFT_ADMIN_PHONE", "RMSOFT_ADMIN_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    assert cli._given_superadmin() is None


def test_a_short_password_creates_nothing(monkeypatch):
    monkeypatch.setenv("RMSOFT_ADMIN_PHONE", "+244923000999")
    monkeypatch.setenv("RMSOFT_ADMIN_PASSWORD", "curta")
    with pytest.raises(SystemExit):
        cli._given_superadmin()
