"""data/graph.py — Граф взаимодействий исполнителей: рёбра, агрегация, скоринг, цепочки.

Рёбра строятся ТОЛЬКО из хронологии событий по issue_id (прямых «кто с кем» в данных нет).
Реворк — атрибут на прямом ребре dev→qa (обратные qa→dev в граф не добавляются).
"""
import hashlib
from typing import Any, Dict, List, Optional

import duckdb
import numpy as np
import pandas as pd

from config import (
    STATUS_ANALYTICS_WAIT,
    STATUS_ANALYTICS_WORK,
    STATUS_ANALYTICS_REVIEW,
    STATUS_DEV_WAIT,
    STATUS_DEV_WORK,
    STATUS_DEV_REVIEW,
    STATUS_QA_WAIT,
    STATUS_QA_WORK,
    STATUS_COMPLETION,
    CORE_ANALYTICS_TEAM,
    CORE_DEV_TEAM,
    CORE_QA_TEAM,
)
from data.task_processor import (
    clean_val,
    extract_deadline_shifts_detail,
    extract_task_type,
)
from utils.time_calc import get_work_minutes

# --- Константы ---------------------------------------------------------------

EDGE_HANDOFF = "handoff"
EDGE_STAGE_TRANSITION = "stage_transition"
EDGE_REVIEW = "review"

STAGE_ANALYTICS = "analytics"
STAGE_DEV = "dev"
STAGE_QA = "qa"

STAGE_LABELS_RU = {
    STAGE_ANALYTICS: "Аналитика",
    STAGE_DEV: "Разработка",
    STAGE_QA: "QA",
    "other": "Прочие",
}

ROLE_LABELS_RU = {
    "analytics": "Аналитик",
    "dev": "Разработчик",
    "qa": "Тестировщик",
    "other": "Прочие",
}

STATUS_FIELDS = ["Текущий статус", "State"]
OPEN_VALUES = {"Open", "Открыта", "Открыт", "Новая", "Новое", "Новый"}
RELEASE_STATUSES = ["Релиз (установка доработок на боевой)", "Завершено"]

REVIEW_STATUSES = set(STATUS_ANALYTICS_REVIEW + STATUS_DEV_REVIEW)

_ANALYTICS_STATUSES = set(STATUS_ANALYTICS_WAIT + STATUS_ANALYTICS_WORK + STATUS_ANALYTICS_REVIEW)
_DEV_STATUSES = set(STATUS_DEV_WAIT + STATUS_DEV_WORK + STATUS_DEV_REVIEW)
_QA_STATUSES = set(STATUS_QA_WAIT + STATUS_QA_WORK + STATUS_COMPLETION)

MIN_ROLE_PAIR_EDGES = 5
MIN_NODE_EDGES = 5

EDGE_COLUMNS = [
    "edge_hash", "issue_id", "from_actor", "from_role", "to_actor", "to_role",
    "edge_type", "stage", "wait_min", "resulted_in_rework", "deadline_slip",
    "ts_from", "ts_to",
]

AGG_COLUMNS = [
    "agg_hash", "from_actor", "from_role", "to_actor", "to_role", "edge_type",
    "stage", "period_months", "cnt", "handoff_count", "rework_count",
    "wait_min_median", "rework_rate", "deadline_slip_rate",
]


def default_team_config() -> Dict[str, List[str]]:
    """Конфиг команд из config.py (по умолчанию — config/team.json)."""
    return {
        "core_analytics_team": list(CORE_ANALYTICS_TEAM),
        "core_dev_team": list(CORE_DEV_TEAM),
        "core_qa_team": list(CORE_QA_TEAM),
    }


# --- Роли --------------------------------------------------------------------

def _norm(name: Any) -> str:
    return str(name or "").strip().casefold()


def _build_role_index(team_config: Dict[str, List[str]]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    mapping = (
        ("core_analytics_team", "analytics"),
        ("core_dev_team", "dev"),
        ("core_qa_team", "qa"),
    )
    for key, role in mapping:
        for member in (team_config or {}).get(key, []) or []:
            n = _norm(member)
            if n:
                index[n] = role
    return index


def resolve_role(actor: Any, team_config: Optional[Dict[str, List[str]]] = None) -> str:
    """Роль автора по config/team.json, иначе 'other'."""
    if team_config is None:
        team_config = default_team_config()
    return _build_role_index(team_config).get(_norm(actor), "other")


def _stage_of_status(to_status: str) -> Optional[str]:
    if to_status in _ANALYTICS_STATUSES:
        return STAGE_ANALYTICS
    if to_status in _DEV_STATUSES:
        return STAGE_DEV
    if to_status in _QA_STATUSES:
        return STAGE_QA
    return None


# --- Постановщик / релиз -----------------------------------------------------

def _status_events(issue_events: pd.DataFrame) -> pd.DataFrame:
    return issue_events[issue_events["changed_value"].isin(STATUS_FIELDS)].sort_values("timestamp")


def get_poster(issue_events: pd.DataFrame) -> Optional[str]:
    """Постановщик = автор первого события перехода Open→*.

    Эвристика (по решению): если явного Open-статуса нет — автор первого события
    смены статуса; если и его нет — автор первого события по timestamp.
    """
    if issue_events is None or issue_events.empty:
        return None
    ev = issue_events.sort_values("timestamp")
    status = _status_events(ev)
    for _, r in status.iterrows():
        if clean_val(r.get("added_values")) in OPEN_VALUES:
            return clean_val(r.get("author_full_name")) or None
    if not status.empty:
        return clean_val(status.iloc[0].get("author_full_name")) or None
    return clean_val(ev.iloc[0].get("author_full_name")) or None


def get_release_actor(issue_events: pd.DataFrame) -> Optional[str]:
    """Автор первого события релиза (added_values ∈ RELEASE_STATUSES)."""
    if issue_events is None or issue_events.empty:
        return None
    status = _status_events(issue_events)
    for _, r in status.iterrows():
        if clean_val(r.get("added_values")) in RELEASE_STATUSES:
            return clean_val(r.get("author_full_name")) or None
    return None


# --- Построение рёбер --------------------------------------------------------

def _edge_hash(issue_id: str, frm: str, to: str, edge_type: str, stage: str, ts_from) -> str:
    key = "|".join([
        str(issue_id), str(frm), str(to), str(edge_type), str(stage),
        str(pd.Timestamp(ts_from)),
    ])
    return hashlib.sha256(key.encode()).hexdigest()


def _detect_rework(ev: pd.DataFrame) -> bool:
    """Возврат QA→Dev после первого попадания в QA (как в task_processor)."""
    status = _status_events(ev)
    seen_qa = False
    for _, r in status.iterrows():
        to_s = clean_val(r.get("added_values"))
        if to_s == "В тестировании":
            seen_qa = True
        elif seen_qa and to_s == "К разработке":
            return True
    return False


def _empty_edges_df() -> pd.DataFrame:
    return pd.DataFrame(columns=EDGE_COLUMNS)


def build_edges(
    events_df: pd.DataFrame,
    team_config: Optional[Dict[str, List[str]]] = None,
    work_start_h: int = 9,
    work_end_h: int = 18,
    net_ratio: float = 0.78,
) -> pd.DataFrame:
    """Строит рёбра графа из событий (без Эпиков).

    wait_min считается один раз на уровне событий (между соседними событиями),
    а не построчно на рёбрах.
    """
    if events_df is None or events_df.empty:
        return _empty_edges_df()

    df = events_df.copy()
    if "task_identifier" not in df.columns:
        if "task_id" in df.columns:
            df["task_identifier"] = df["task_id"]
        else:
            return _empty_edges_df()
    if "timestamp" not in df.columns or "changed_value" not in df.columns:
        return _empty_edges_df()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    role_index = _build_role_index(team_config if team_config is not None else default_team_config())

    rows: List[Dict[str, Any]] = []
    for tid, task_df in df.groupby("task_identifier", sort=False):
        if extract_task_type(task_df) == "Эпик":
            continue
        rows.extend(_task_edges(str(tid), task_df, role_index, work_start_h, work_end_h, net_ratio))

    if not rows:
        return _empty_edges_df()
    return pd.DataFrame(rows, columns=EDGE_COLUMNS)


def _task_edges(
    task_id: str,
    task_df: pd.DataFrame,
    role_index: Dict[str, str],
    work_start_h: int,
    work_end_h: int,
    net_ratio: float,
) -> List[Dict[str, Any]]:
    ev = task_df.sort_values("timestamp").reset_index(drop=True)

    # Стадия каждого события из таймлайна статусов.
    stages: List[Optional[str]] = []
    cur: Optional[str] = None
    for _, r in ev.iterrows():
        if str(r.get("changed_value")) in STATUS_FIELDS:
            s = _stage_of_status(clean_val(r.get("added_values")))
            if s is not None:
                cur = s
        stages.append(cur)

    # Слитные «прогоны» одной стадии.
    runs: List[Dict[str, Any]] = []
    for i, stage in enumerate(stages):
        if stage is None:
            continue
        if runs and runs[-1]["stage"] == stage:
            runs[-1]["events"].append(i)
        else:
            runs.append({"stage": stage, "events": [i]})
    if not runs:
        return []

    def author(i: int) -> str:
        return clean_val(ev.iloc[i].get("author_full_name")) or "Не указан"

    def ts(i: int) -> pd.Timestamp:
        return ev.iloc[i]["timestamp"]

    shifts = extract_deadline_shifts_detail(task_df)
    shift_ts = {
        pd.Timestamp(s["ts"])
        for s in shifts
        if s["deadline_before"] is not None and s["deadline_after"] != s["deadline_before"]
    }
    run_has_slip = [any(ts(i) in shift_ts for i in run["events"]) for run in runs]
    has_rework = _detect_rework(ev)

    edges: List[Dict[str, Any]] = []

    def add(frm: str, to: str, etype: str, stage: str, t_from, t_to,
            slip: bool = False) -> None:
        if not frm or not to or frm == to:
            return
        wait = get_work_minutes(pd.Timestamp(t_from), pd.Timestamp(t_to),
                                work_start_h, work_end_h, net_ratio)
        edges.append({
            "edge_hash": _edge_hash(task_id, frm, to, etype, stage, t_from),
            "issue_id": task_id,
            "from_actor": frm,
            "from_role": role_index.get(_norm(frm), "other"),
            "to_actor": to,
            "to_role": role_index.get(_norm(to), "other"),
            "edge_type": etype,
            "stage": stage,
            "wait_min": float(wait),
            "resulted_in_rework": False,
            "deadline_slip": bool(slip),
            "ts_from": pd.Timestamp(t_from),
            "ts_to": pd.Timestamp(t_to),
        })

    # (a) handoff / (c) review — смена автора внутри одной стадии.
    for run in runs:
        idxs = run["events"]
        for k in range(1, len(idxs)):
            i_prev, i_cur = idxs[k - 1], idxs[k]
            a_prev, a_cur = author(i_prev), author(i_cur)
            if a_prev == a_cur:
                continue
            to_status = clean_val(ev.iloc[i_cur].get("added_values"))
            etype = EDGE_REVIEW if to_status in REVIEW_STATUSES else EDGE_HANDOFF
            add(a_prev, a_cur, etype, run["stage"], ts(i_prev), ts(i_cur))

    # (b) stage_transition — last(A) → first(B). Обратные qa→dev (по ролям) не создаём.
    for k in range(1, len(runs)):
        run_a, run_b = runs[k - 1], runs[k]
        frm = author(run_a["events"][-1])
        to = author(run_b["events"][0])
        from_role = role_index.get(_norm(frm), "other")
        to_role = role_index.get(_norm(to), "other")
        if from_role == STAGE_QA and to_role == STAGE_DEV:
            continue
        add(frm, to, EDGE_STAGE_TRANSITION, run_b["stage"],
            ts(run_a["events"][-1]), ts(run_b["events"][0]), slip=run_has_slip[k])

    # (d) resulting rework — флаг на первом прямом ребре dev→qa (по ролям).
    if has_rework:
        for edge in edges:
            if edge["from_role"] == STAGE_DEV and edge["to_role"] == STAGE_QA:
                edge["resulted_in_rework"] = True
                break

    return edges


# --- Агрегация ---------------------------------------------------------------

def _empty_agg_df() -> pd.DataFrame:
    return pd.DataFrame(columns=AGG_COLUMNS)


def aggregate_edges(edges_df: pd.DataFrame, period_months: int = 6) -> pd.DataFrame:
    """Агрегирует рёбра за последние N месяцев (якорь — max(ts_to) в данных)."""
    if edges_df is None or edges_df.empty:
        return _empty_agg_df()

    df = edges_df.copy()
    df["ts_to"] = pd.to_datetime(df["ts_to"], errors="coerce")
    anchor = df["ts_to"].max()
    if pd.notna(anchor):
        cutoff = anchor - pd.DateOffset(months=int(period_months))
        df = df[df["ts_to"] >= cutoff]
    if df.empty:
        return _empty_agg_df()

    for col in ("resulted_in_rework", "deadline_slip"):
        if col not in df.columns:
            df[col] = False
        df[col] = df[col].fillna(False).astype(bool)

    conn = duckdb.connect(":memory:")
    conn.register("e", df)
    agg = conn.execute("""
        SELECT
            from_actor, from_role, to_actor, to_role, edge_type, stage,
            COUNT(*) AS cnt,
            COUNT(*) AS handoff_count,
            SUM(CASE WHEN resulted_in_rework THEN 1 ELSE 0 END) AS rework_count,
            median(wait_min) AS wait_min_median,
            AVG(CASE WHEN deadline_slip THEN 1.0 ELSE 0.0 END) AS deadline_slip_rate
        FROM e
        GROUP BY from_actor, from_role, to_actor, to_role, edge_type, stage
    """).df()
    conn.close()

    if agg.empty:
        return _empty_agg_df()

    agg["period_months"] = int(period_months)
    agg["cnt"] = agg["cnt"].astype(int)
    agg["handoff_count"] = agg["handoff_count"].astype(int)
    agg["rework_count"] = agg["rework_count"].astype(int)
    agg["rework_rate"] = np.where(
        agg["handoff_count"] > 0, agg["rework_count"] / agg["handoff_count"], 0.0
    )
    agg["deadline_slip_rate"] = agg["deadline_slip_rate"].fillna(0.0)
    agg["agg_hash"] = agg.apply(
        lambda r: hashlib.sha256(
            f"{r['from_actor']}|{r['to_actor']}|{r['edge_type']}|{r['stage']}|{int(period_months)}".encode()
        ).hexdigest(),
        axis=1,
    )
    return agg[AGG_COLUMNS]


# --- Скоринг ----------------------------------------------------------------

def _robust_z(values: pd.Series) -> pd.Series:
    s = pd.Series(values, dtype="float64")
    if s.empty:
        return s
    med = s.median()
    mad = (s - med).abs().median()
    if mad and not pd.isna(mad) and mad > 0:
        return (s - med) / (1.4826 * mad)
    std = s.std(ddof=0)
    if std and not pd.isna(std) and std > 0:
        return (s - med) / std
    return pd.Series(0.0, index=s.index)


def _group_z(df: pd.DataFrame, key: str, values: pd.Series) -> pd.Series:
    out = pd.Series(0.0, index=df.index)
    for _, idx in df.groupby(key).groups.items():
        out.loc[idx] = _robust_z(values.loc[idx])
    return out


def score_edges(agg_df: pd.DataFrame) -> pd.DataFrame:
    """z-скоринг рёбер по role_pair: E = z_speed + z_quality + z_reliability."""
    if agg_df is None or agg_df.empty:
        out = _empty_agg_df()
        out["z_speed"] = []
        out["z_quality"] = []
        out["z_reliability"] = []
        out["E"] = []
        out["insufficient_data"] = []
        return out

    df = agg_df.copy()
    df["from_role"] = df["from_role"].fillna("other")
    df["to_role"] = df["to_role"].fillna("other")
    df["role_pair"] = df["from_role"] + "->" + df["to_role"]

    pair_n = df.groupby("role_pair")["cnt"].transform("sum")
    df["insufficient_data"] = pair_n < MIN_ROLE_PAIR_EDGES

    speed_raw = -df["wait_min_median"].astype("float64")
    quality_raw = 1.0 - df["rework_rate"].astype("float64").fillna(0.0)
    reliability_raw = 1.0 - df["deadline_slip_rate"].astype("float64").fillna(0.0)

    df["z_speed"] = _group_z(df, "role_pair", speed_raw)
    df["z_quality"] = _group_z(df, "role_pair", quality_raw)
    df["z_reliability"] = _group_z(df, "role_pair", reliability_raw)
    df["E"] = df["z_speed"] + df["z_quality"] + df["z_reliability"]

    mask = df["insufficient_data"].astype(bool)
    df.loc[mask, ["z_speed", "z_quality", "z_reliability", "E"]] = np.nan
    return df


def score_nodes(scored_df: pd.DataFrame, edges_df: pd.DataFrame) -> pd.DataFrame:
    """Агрегат исходящих рёбер узла: z-score относительно своей роли + rework_rate."""
    cols = ["actor", "role", "z_score", "rework_rate_node", "insufficient_data_node", "out_count"]
    if edges_df is None or edges_df.empty:
        return pd.DataFrame(columns=cols)

    out = edges_df.copy()
    out["from_role"] = out["from_role"].fillna("other")
    out["_rework"] = out["resulted_in_rework"].fillna(False).astype(int)

    grp = out.groupby(["from_actor", "from_role"], as_index=False).agg(
        out_count=("edge_hash", "count"),
        rework=("_rework", "sum"),
    )

    e_mean = pd.DataFrame(columns=["from_actor", "from_role", "E_mean"])
    if scored_df is not None and not scored_df.empty and "E" in scored_df.columns:
        merged = out.merge(
            scored_df[["from_actor", "to_actor", "edge_type", "stage", "E"]],
            on=["from_actor", "to_actor", "edge_type", "stage"],
            how="left",
        )
        merged = merged.dropna(subset=["E"])
        if not merged.empty:
            e_mean = (
                merged.groupby(["from_actor", "from_role"], as_index=False)["E"].mean()
                .rename(columns={"E": "E_mean"})
            )

    grp = grp.merge(e_mean, on=["from_actor", "from_role"], how="left")

    grp["z_score"] = 0.0
    for _, idx in grp.groupby("from_role").groups.items():
        grp.loc[idx, "z_score"] = _robust_z(grp.loc[idx, "E_mean"].fillna(0.0))

    grp["rework_rate_node"] = np.where(
        grp["out_count"] > 0, grp["rework"] / grp["out_count"], 0.0
    )
    grp["insufficient_data_node"] = grp["out_count"] < MIN_NODE_EDGES
    grp = grp.rename(columns={"from_actor": "actor", "from_role": "role"})
    return grp[cols]


# --- Поиск цепочек -----------------------------------------------------------

def _enumerate_paths(
    adj: Dict[str, List[tuple]],
    source: str,
    target: str,
    max_depth: int,
    max_paths: int,
) -> List[tuple]:
    """Все простые пути source→target длиной ≤ max_depth (DFS с отсечением)."""
    found: List[tuple] = []
    stack = [(source, [source], 0.0, 0.0)]
    while stack:
        node, path, cost, total_e = stack.pop()
        if node == target and len(path) >= 2:
            found.append((list(path), cost, total_e))
            if len(found) >= max_paths:
                break
            continue
        if len(path) - 1 >= max_depth:
            continue
        for nxt, c, ce in adj.get(node, []):
            if nxt in path:
                continue
            stack.append((nxt, path + [nxt], cost + c, total_e + ce))
    return found


def find_chains(
    scored_df: pd.DataFrame,
    edges_df: Optional[pd.DataFrame] = None,
    from_actor: Optional[str] = None,
    to_actor: Optional[str] = None,
    top_n: int = 5,
    depth: int = 8,
    max_paths: int = 20000,
) -> Dict[str, List[Dict[str, Any]]]:
    """Топ-N «здоровых» (min cost) и «проблемных» (max cost) цепочек акторов.

    cost = C - E (C = max(E)+eps) → Dijkstra-совместимые положительные веса;
    здоровые = кратчайшие по cost (максимум E), проблемные = самые дорогие.
    Рёбра с insufficient_data исключаются.
    """
    result: Dict[str, List[Dict[str, Any]]] = {"healthy": [], "problem": []}
    if scored_df is None or scored_df.empty or not from_actor or not to_actor:
        return result

    df = scored_df.copy()
    if "insufficient_data" in df.columns:
        df = df[~df["insufficient_data"].fillna(False).astype(bool)]
    df = df.dropna(subset=["E"])
    if df.empty:
        return result

    pairs = (
        df.groupby(["from_actor", "to_actor"], as_index=False)["E"].mean()
    )
    if pairs.empty:
        return result

    max_e = max(float(pairs["E"].max()), 0.0)
    eps = 1e-9
    adj: Dict[str, List[tuple]] = {}
    for _, r in pairs.iterrows():
        cost = (max_e + eps) - float(r["E"])
        adj.setdefault(r["from_actor"], []).append((r["to_actor"], cost, float(r["E"])))
    for node in adj:
        adj[node].sort(key=lambda x: x[0])

    paths = _enumerate_paths(adj, from_actor, to_actor, int(depth), int(max_paths))

    def pack(p: tuple) -> Dict[str, Any]:
        actors, total_cost, total_e = p
        return {
            "actors": actors,
            "total_E": round(total_e, 4),
            "total_cost": round(total_cost, 4),
            "edge_count": len(actors) - 1,
        }

    healthy = sorted(paths, key=lambda p: p[1])[:int(top_n)]
    problem = sorted(paths, key=lambda p: p[1], reverse=True)[:int(top_n)]
    result["healthy"] = [pack(p) for p in healthy]
    result["problem"] = [pack(p) for p in problem]
    return result
