"""Уникальные задачи в очереди QA за сутки и их среднее по рабочим дням."""
from functools import lru_cache
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pandas as pd

from data.task_processor import clean_val

CALENDAR_DIR = Path(__file__).resolve().parents[1] / "config/production_calendar"


@lru_cache(maxsize=None)
def _calendar(year: int) -> dict[str, str]:
    path = CALENDAR_DIR / f"{year}.xml"
    if not path.exists():
        raise ValueError(f"Нет производственного календаря РФ за {year} год.")
    return {day.attrib["d"]: day.attrib["t"] for day in ET.parse(path).findall("days/day")}


def is_workday(day: pd.Timestamp) -> bool:
    kind = _calendar(day.year).get(day.strftime("%m.%d"))
    return kind in ("2", "3") if kind is not None else day.weekday() < 5


def local_timestamp(value, timezone: str = "Asia/Yekaterinburg") -> pd.Timestamp:
    """Даты без зоны в БД уже считаются локальным временем команды."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(timezone).tz_localize(None)
    return ts


def build_queue_daily(events: pd.DataFrame, complete_through, start_date=None,
                      end_date=None, now=None, timezone="Asia/Yekaterinburg",
                      excluded_task_ids=()) -> pd.DataFrame:
    """Считать только полные сутки до подтверждённой даты полноты включительно.

    Интервалы полуоткрытые [вход, выход). Открытые интервалы ограничиваются
    датой полноты; фильтрация периода выполняется после восстановления истории.
    """
    empty = pd.DataFrame(columns=["date", "tasks"])
    if events is None or events.empty:
        return empty
    current = local_timestamp(now if now is not None else pd.Timestamp.now(tz=timezone), timezone)
    cutoff = min(local_timestamp(complete_through, timezone).normalize() + pd.Timedelta(days=1),
                 current.normalize())
    history = events.copy()
    history["timestamp"] = history["timestamp"].map(lambda x: local_timestamp(x, timezone))
    history = history.dropna(subset=["timestamp"])
    if history.empty:
        return empty
    first = history["timestamp"].min().normalize()
    if start_date is not None:
        first = max(first, local_timestamp(start_date, timezone).normalize())
    if end_date is not None:
        cutoff = min(cutoff, local_timestamp(end_date, timezone).normalize() + pd.Timedelta(days=1))
    if first >= cutoff:
        return empty
    days = pd.date_range(first, cutoff - pd.Timedelta(days=1), freq="D")
    days = pd.DatetimeIndex([d for d in days if is_workday(d)])
    counts = pd.Series(0, index=days, dtype="int64")
    statuses = history[history["changed_value"].isin(["Текущий статус", "State"])]
    # В выгрузке закрытие иногда записано отдельным событием без смены статуса.
    if "activity_type" in history:
        resolved = history[history["activity_type"] == "IssueResolvedActivityItem"].copy()
        resolved["added_values"] = ""
        statuses = pd.concat([statuses, resolved], ignore_index=True)
    task_col = "task_identifier" if "task_identifier" in statuses else "task_id"
    excluded = {str(task_id) for task_id in excluded_task_ids}
    for task_id, task in statuses.groupby(task_col, sort=False):
        if str(task_id) in excluded:
            continue
        task = task.sort_values("timestamp", kind="stable").drop_duplicates(
            ["timestamp", "added_values", "removed_values"])
        starts = task["timestamp"].tolist()
        ends = starts[1:] + [cutoff]
        seen = pd.Series(False, index=days)
        for status, begin, finish in zip(task["added_values"], starts, ends):
            if clean_val(status) == "К тестированию" and finish > begin:
                seen |= (days < finish) & (days + pd.Timedelta(days=1) > begin)
        counts += seen.astype("int64")
    return pd.DataFrame({"date": days, "tasks": counts.to_numpy()})


def task_texts(events: pd.DataFrame) -> pd.DataFrame:
    """Последнее известное название и описание; прежние версии не классифицируют задачу."""
    task_col = "task_identifier" if "task_identifier" in events else "task_id"
    result = pd.DataFrame(index=pd.Index(events[task_col].dropna().astype(str).unique(), name="task_id"))
    fields = {
        "title": {"summary", "title", "название", "название задачи", "заголовок"},
        "description": {"description", "описание", "описание задачи"},
    }
    names = events["changed_value"].fillna("").astype(str).str.strip().str.casefold()
    for column, aliases in fields.items():
        rows = events[names.isin(aliases)].sort_values("timestamp", kind="stable").copy()
        rows["_task"] = rows[task_col].astype(str)
        latest = rows.drop_duplicates("_task", keep="last").set_index("_task")
        result[column] = latest["added_values"].map(clean_val).reindex(result.index).fillna("")
    result["has_text"] = (result["title"].str.strip() != "") | (result["description"].str.strip() != "")
    return result


def matching_task_ids(texts: pd.DataFrame, keywords) -> set[str]:
    words = [str(word).strip() for word in keywords if str(word).strip()]
    if not words or texts.empty:
        return set()
    pattern = r"(?<!\w)(?:" + "|".join(re.escape(word) for word in words) + r")(?!\w)"
    content = texts["title"] + "\n" + texts["description"]
    return set(texts.index[content.str.contains(pattern, case=False, regex=True)].astype(str))


def build_queue_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=["month", "average", "workdays", "last_day"])
    return daily.assign(month=daily["date"].dt.to_period("M").dt.to_timestamp()).groupby(
        "month", as_index=False).agg(average=("tasks", "mean"), workdays=("tasks", "size"),
                                    last_day=("date", "max"))
