"""Проверка доступа к вкладке «Дашборд»."""
from access_control import get_available_tabs, get_tab_labels


def test_dashboard_is_available_only_to_admin():
    assert "dashboard" in get_available_tabs("admin")
    for role in ("guest", "analyst", "developer", "tester"):
        assert "dashboard" not in get_available_tabs(role)


def test_dashboard_is_first_admin_tab():
    assert get_available_tabs("admin")[0] == "dashboard"


def test_dashboard_has_label():
    assert get_tab_labels()["dashboard"] == "Дашборд"
