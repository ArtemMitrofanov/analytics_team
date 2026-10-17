"""tests/test_graph.py — тесты графа взаимодействий (data/graph.py, db.py)."""
import pandas as pd
import pytest

from data.graph import (
    build_edges,
    aggregate_edges,
    score_edges,
    score_nodes,
    find_chains,
    get_poster,
    get_release_actor,
    resolve_role,
)
from data.task_processor import extract_deadline_shifts_detail
from utils.time_calc import get_work_minutes
from access_control import get_available_tabs, ALL_TABS, TAB_LABELS

TEAM = {
    "core_analytics_team": ["Анна", "Елена"],
    "core_dev_team": ["Дмитрий", "Пётр"],
    "core_qa_team": ["Ксения"],
}


def _events(rows):
    df = pd.DataFrame(rows, columns=[
        "task_identifier", "timestamp", "changed_value",
        "added_values", "removed_values", "author_full_name",
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def _status(tid, ts, to_status, from_status, author):
    return (tid, ts, "Текущий статус", to_status, from_status, author)


# --- Построение рёбер --------------------------------------------------------

class TestBuildEdges:
    def test_build_handoff_edge(self):
        df = _events([
            _status("T1", "2024-01-01 09:00", "В аналитике", "К аналитике", "Анна"),
            _status("T1", "2024-01-01 11:00", "В аналитике", "В аналитике", "Елена"),
        ])
        edges = build_edges(df, TEAM)
        handoffs = edges[edges["edge_type"] == "handoff"]
        assert len(handoffs) == 1
        row = handoffs.iloc[0]
        assert row["from_actor"] == "Анна" and row["to_actor"] == "Елена"
        assert row["wait_min"] > 0

    def test_build_stage_transition(self):
        df = _events([
            _status("T1", "2024-01-01 09:00", "В аналитике", "К аналитике", "Анна"),
            _status("T1", "2024-01-02 09:00", "В разработке", "В аналитике", "Дмитрий"),
        ])
        edges = build_edges(df, TEAM)
        trans = edges[edges["edge_type"] == "stage_transition"]
        assert len(trans) == 1
        row = trans.iloc[0]
        assert row["from_actor"] == "Анна" and row["to_actor"] == "Дмитрий"
        assert row["stage"] == "dev"

    def test_build_review_edge(self):
        df = _events([
            _status("T1", "2024-01-01 09:00", "В разработке", "К разработке", "Дмитрий"),
            _status("T1", "2024-01-01 11:00", "К ревью (разработка)", "В разработке", "Пётр"),
        ])
        edges = build_edges(df, TEAM)
        reviews = edges[edges["edge_type"] == "review"]
        assert len(reviews) == 1
        assert reviews.iloc[0]["from_actor"] == "Дмитрий"
        assert reviews.iloc[0]["to_actor"] == "Пётр"

    def test_resulted_in_rework(self):
        df = _events([
            _status("T1", "2024-01-01 09:00", "В разработке", "К разработке", "Дмитрий"),
            _status("T1", "2024-01-02 09:00", "К тестированию", "В разработке", "Дмитрий"),
            _status("T1", "2024-01-03 09:00", "В тестировании", "К тестированию", "Ксения"),
            _status("T1", "2024-01-04 09:00", "К разработке", "В тестировании", "Ксения"),
            _status("T1", "2024-01-05 09:00", "К тестированию", "К разработке", "Дмитрий"),
        ])
        edges = build_edges(df, TEAM)
        reworked = edges[edges["resulted_in_rework"]]
        assert len(reworked) == 1
        row = reworked.iloc[0]
        assert row["from_role"] == "dev" and row["to_role"] == "qa"

    def test_epic_filtered(self):
        df = _events([
            ("T1", "2024-01-01 08:00", "Тип работы", "Epic", "", "Анна"),
            _status("T1", "2024-01-01 09:00", "В аналитике", "К аналитике", "Анна"),
            _status("T1", "2024-01-01 11:00", "В аналитике", "В аналитике", "Елена"),
        ])
        assert build_edges(df, TEAM).empty

    def test_wait_min_events_level(self):
        df = _events([
            _status("T1", "2024-01-01 09:00", "В аналитике", "К аналитике", "Анна"),
            _status("T1", "2024-01-01 11:00", "В аналитике", "В аналитике", "Елена"),
        ])
        edges = build_edges(df, TEAM)
        expected = get_work_minutes(
            pd.Timestamp("2024-01-01 09:00"), pd.Timestamp("2024-01-01 11:00"), 9, 18, 0.78
        )
        assert edges.iloc[0]["wait_min"] == pytest.approx(expected)

    def test_deadline_slip_on_stage(self):
        df = _events([
            _status("T1", "2024-01-01 09:00", "В аналитике", "К аналитике", "Анна"),
            ("T1", "2024-01-01 11:00", "Дедлайн заказчика", "1704067200000", "", "Анна"),
            _status("T1", "2024-01-02 09:00", "В разработке", "В аналитике", "Дмитрий"),
            ("T1", "2024-01-05 09:00", "Дедлайн заказчика", "1704499200000", "1704067200000", "Дмитрий"),
            _status("T1", "2024-01-06 09:00", "К тестированию", "В разработке", "Дмитрий"),
        ])
        edges = build_edges(df, TEAM)
        slipped = edges[edges["deadline_slip"]]
        assert len(slipped) == 1
        row = slipped.iloc[0]
        assert row["edge_type"] == "stage_transition" and row["stage"] == "dev"


# --- Постановщик / релиз -----------------------------------------------------

class TestPosterRelease:
    def test_get_poster_open_event(self):
        df = _events([
            _status("T1", "2024-01-01 09:00", "В аналитике", "Open", "Анна"),
            _status("T1", "2024-01-01 11:00", "В разработке", "В аналитике", "Дмитрий"),
        ])
        assert get_poster(df) == "Анна"

    def test_get_poster_fallback(self):
        df = _events([
            ("T1", "2024-01-01 09:00", "Приоритет по задаче", "Обычный", "", "Пётр"),
            ("T1", "2024-01-01 10:00", "Комментарий", "текст", "", "Анна"),
        ])
        assert get_poster(df) == "Пётр"

    def test_get_release_actor(self):
        df = _events([
            _status("T1", "2024-01-01 09:00", "В аналитике", "К аналитике", "Анна"),
            _status("T1", "2024-01-02 09:00", "Завершено", "Протестировано", "Ксения"),
        ])
        assert get_release_actor(df) == "Ксения"


# --- Скоринг -----------------------------------------------------------------

def _agg_row(frm, to, from_role, to_role, wait, rework, slip, etype="handoff", stage="dev"):
    return {
        "agg_hash": f"{frm}|{to}|{etype}|{stage}",
        "from_actor": frm, "from_role": from_role,
        "to_actor": to, "to_role": to_role,
        "edge_type": etype, "stage": stage,
        "period_months": 6, "cnt": 1, "handoff_count": 1, "rework_count": rework,
        "wait_min_median": wait, "rework_rate": rework, "deadline_slip_rate": slip,
    }


class TestScoring:
    def test_zscore_and_insufficient(self):
        small = pd.DataFrame([_agg_row(f"d{i}", f"q{i}", "dev", "qa", 100, 0, 0) for i in range(3)])
        scored_small = score_edges(small)
        assert scored_small["insufficient_data"].all()
        assert scored_small["E"].isna().all()

        big = pd.DataFrame([
            _agg_row(f"d{i}", f"q{i}", "dev", "qa", 100 + i, i % 2, 0) for i in range(10)
        ])
        scored_big = score_edges(big)
        assert not scored_big["insufficient_data"].any()
        assert scored_big["E"].notna().all()

    def test_insufficient_data_node(self):
        edges = pd.DataFrame({
            "edge_hash": ["e1", "e2"],
            "from_actor": ["Дмитрий", "Дмитрий"],
            "from_role": ["dev", "dev"],
            "to_actor": ["Ксения", "Пётр"],
            "to_role": ["qa", "dev"],
            "edge_type": ["handoff", "handoff"],
            "stage": ["qa", "dev"],
            "resulted_in_rework": [False, True],
        })
        nodes = score_nodes(pd.DataFrame(), edges)
        row = nodes[nodes["actor"] == "Дмитрий"].iloc[0]
        assert row["insufficient_data_node"] is True or bool(row["insufficient_data_node"])
        assert row["out_count"] == 2


# --- Цепочки -----------------------------------------------------------------

class TestFindChains:
    def _scored(self):
        return pd.DataFrame([
            # A -> B -> D : здоровый (высокий E)
            {"from_actor": "A", "to_actor": "B", "E": 3.0, "insufficient_data": False},
            {"from_actor": "B", "to_actor": "D", "E": 3.0, "insufficient_data": False},
            # A -> C -> D : проблемный (низкий E)
            {"from_actor": "A", "to_actor": "C", "E": -3.0, "insufficient_data": False},
            {"from_actor": "C", "to_actor": "D", "E": -3.0, "insufficient_data": False},
        ])

    def test_find_chains_healthy(self):
        chains = find_chains(self._scored(), from_actor="A", to_actor="D", top_n=1)
        assert chains["healthy"][0]["actors"] == ["A", "B", "D"]

    def test_find_chains_problem(self):
        chains = find_chains(self._scored(), from_actor="A", to_actor="D", top_n=1)
        assert chains["problem"][0]["actors"] == ["A", "C", "D"]

    def test_find_chains_excludes_insufficient(self):
        scored = self._scored()
        scored.loc[scored["to_actor"] == "B", "insufficient_data"] = True
        chains = find_chains(scored, from_actor="A", to_actor="D", top_n=5)
        assert all("B" not in c["actors"] for c in chains["healthy"] + chains["problem"])


# --- Дедлайны (новая функция) ------------------------------------------------

class TestDeadlineShiftsDetail:
    def test_detail_records_shifts(self):
        df = _events([
            ("T1", "2024-01-01 11:00", "Дедлайн заказчика", "1704067200000", "", "Анна"),
            ("T1", "2024-01-05 11:00", "Дедлайн заказчика", "1704499200000", "1704067200000", "Дмитрий"),
        ])
        detail = extract_deadline_shifts_detail(df)
        assert len(detail) == 2
        assert detail[0]["deadline_before"] is None
        assert detail[1]["deadline_before"] is not None
        assert detail[1]["deadline_after"] > detail[0]["deadline_after"]


# --- Роли и доступ -----------------------------------------------------------

class TestRolesAndAccess:
    def test_resolve_role(self):
        assert resolve_role("Дмитрий", TEAM) == "dev"
        assert resolve_role("Ксения", TEAM) == "qa"
        assert resolve_role("Анна", TEAM) == "analytics"
        assert resolve_role("Ноунейм", TEAM) == "other"

    def test_admin_gate(self):
        assert "graph" in get_available_tabs("admin")
        assert "graph" not in get_available_tabs("analyst")
        assert "graph" not in get_available_tabs("developer")
        assert "graph" not in get_available_tabs("tester")
        assert "graph" not in get_available_tabs("guest")
        assert TAB_LABELS["graph"] == "Граф взаимодействий"
        assert "graph" in ALL_TABS


# --- DuckDB: upsert/чтение/fingerprint ---------------------------------------

class TestGraphDb:
    @pytest.fixture
    def graph_db(self, tmp_path, monkeypatch):
        import db as db_module
        monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "graph_test.duckdb")
        db_module.clear_graph_edges()
        yield db_module
        db_module.clear_graph_edges()

    def test_upsert_and_read(self, graph_db):
        db = graph_db
        df = _events([
            _status("T1", "2024-01-01 09:00", "В аналитике", "К аналитике", "Анна"),
            _status("T1", "2024-01-02 09:00", "В разработке", "В аналитике", "Дмитрий"),
        ])
        edges = build_edges(df, TEAM)
        assert db.upsert_graph_edges(edges) == len(edges)
        stored = db.get_graph_edges()
        assert len(stored) == len(edges)

    def test_upsert_idempotent(self, graph_db):
        db = graph_db
        df = _events([
            _status("T1", "2024-01-01 09:00", "В аналитике", "К аналитике", "Анна"),
            _status("T1", "2024-01-02 09:00", "В разработке", "В аналитике", "Дмитрий"),
        ])
        edges = build_edges(df, TEAM)
        db.upsert_graph_edges(edges)
        db.upsert_graph_edges(edges)
        assert len(db.get_graph_edges()) == len(edges)

    def test_agg_upsert_and_fingerprint(self, graph_db):
        db = graph_db
        df = _events([
            _status("T1", "2024-01-01 09:00", "В аналитике", "К аналитике", "Анна"),
            _status("T1", "2024-01-02 09:00", "В разработке", "В аналитике", "Дмитрий"),
        ])
        edges = build_edges(df, TEAM)
        db.upsert_graph_edges(edges)
        agg = aggregate_edges(edges, 6)
        if not agg.empty:
            db.upsert_graph_edges_agg(agg)
            assert len(db.get_graph_edges_agg(6)) == len(agg)

        fp = db.get_graph_fingerprint()
        assert fp == db.get_graph_fingerprint()
        assert db.get_graph_agg_fingerprint(6) != db.get_graph_agg_fingerprint(12)

    def test_invalidate_flag(self, graph_db):
        db = graph_db
        assert db.is_graph_dirty() is False
        db.invalidate_graph()
        assert db.is_graph_dirty() is True
