import pandas as pd
import pytest

from config import Team
from data.team_import import WrongTeamImport, check_import_subsystem


def test_shared_project_is_routed_by_latest_subsystem():
    teams = {
        "msfo": Team("МСФО", project="KBAKontur", subsystem="МСФО. п00272"),
        "modern": Team("Модернизация", project="KBAKontur", subsystem="Модернизация. п00277"),
        "combined": Team("KBAKontur"),
    }
    frame = pd.DataFrame([
        ("KBAKontur-1", "2026-02-01", "Subsystem", "['Модернизация. п00277']"),
        ("KBAKontur-1", "2026-01-01", "Subsystem", "['МСФО. п00272']"),
        ("KBAKontur-2", "2026-01-05", "State", "В разработке"),
    ], columns=["issue_id", "timestamp", "changed_value", "added_values"])

    assert check_import_subsystem(frame, "modern", "KBAKontur", teams)
    for other_team in ("msfo", "combined"):
        with pytest.raises(WrongTeamImport, match="Файл относится к команде «Модернизация»"):
            check_import_subsystem(frame, other_team, "KBAKontur", teams)

    frame.loc[2, ["changed_value", "added_values"]] = ["Subsystem", "['МСФО. п00272']"]
    with pytest.raises(WrongTeamImport, match="ожидается Subsystem"):
        check_import_subsystem(frame, "modern", "KBAKontur", teams)
