"""data/metrics.py — Пересчёт сводных метрик этапа за выбранный период."""
from typing import Optional
import pandas as pd
from utils.time_calc import get_work_minutes
from config import STATUS_ANALYTICS_REVIEW, STATUS_DEV_REVIEW


def _sum_interval_days(sub: pd.DataFrame, start_col: str, end_col: str, work_start_h, work_end_h, net_ratio, net_day_hours) -> float:
    total_mins = 0.0
    for _, r in sub.iterrows():
        t1 = r.get(start_col)
        t2 = r.get(end_col)
        if pd.isna(t1) or pd.isna(t2):
            continue
        total_mins += get_work_minutes(pd.Timestamp(t1), pd.Timestamp(t2), work_start_h, work_end_h, net_ratio)
    return total_mins / 60.0 / net_day_hours


def _filter_intervals_by_period(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    """Фильтрует DataFrame интервалов (колонки Задача/Начало/Завершение) по периоду."""
    if df is None or df.empty or "Задача" not in df.columns or "Начало" not in df.columns:
        return pd.DataFrame(columns=["Задача", "Начало_ts", "Завершение_ts"])
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    df = df.copy()
    df["Начало_ts"] = pd.to_datetime(df["Начало"])
    df["Завершение_ts"] = pd.to_datetime(df["Завершение"])
    return df[(df["Начало_ts"] < end_ts) & (df["Завершение_ts"] >= start_ts)]


def recompute_role_period_metrics(
    summary_df: pd.DataFrame,
    iters: pd.DataFrame,
    revs: pd.DataFrame,
    role: str,
    start_date,
    end_date,
    work_start_h: int,
    work_end_h: int,
    net_ratio: float,
    net_day_hours: float,
    wait_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Пересчитывает метрики этапа (работа/очередь/циклтайм/flow) по итерациям,
    пересекающимся с периодом [start_date, end_date]. Возвращает новый DataFrame
    с теми же колонками, что у summary_df, и строками только для задач с активностью.

    Для роли QA очередь («К тестированию») считается из wait_df, если передана."""
    if summary_df.empty:
        return summary_df.copy()

    it_in = _filter_intervals_by_period(iters, start_date, end_date)
    rv_in = _filter_intervals_by_period(revs, start_date, end_date)
    if role == "qa" and wait_df is not None:
        wt_in = _filter_intervals_by_period(wait_df, start_date, end_date)
    else:
        wt_in = pd.DataFrame(columns=["Задача", "Начало_ts", "Завершение_ts"])

    if role == "qa":
        work_col = "В тестировании (дни)"
        queue_col = "Очередь ожидания QA (дни)"
        cycle_col = "Циклтайм QA (дни)"
        flow_col = "Flow Efficiency QA (%)"
        other_col = "Доработки у dev (дни)"
        iter_col = "Итераций QA"
        wait_col = None
        rev_col = None
        review_wait_col = None
    elif role == "dev":
        work_col = "В разработке (д.)"
        queue_col = "Очередь/Код Ревью Dev (д.)"
        cycle_col = "Цикл Разработки (д.)"
        flow_col = "Flow Разработки (%)"
        other_col = None
        iter_col = None
        wait_col = "К разработке (д.)"
        rev_col = "Ревью кода (д.)"
        review_wait_col = "К ревью (разработка) (д.)"
    elif role == "an":
        work_col = "В аналитике (д.)"
        queue_col = "Очередь/Ревью Аналитики (д.)"
        cycle_col = "Цикл Аналитики (д.)"
        flow_col = "Flow Аналитики (%)"
        other_col = None
        iter_col = None
        wait_col = "К аналитике (д.)"
        rev_col = "Ревью аналитики (д.)"
        review_wait_col = "К ревью (аналитика) (д.)"
    else:
        raise ValueError(f"Неизвестная роль: {role}")

    result_rows = []
    for tid in it_in["Задача"].unique():
        row = summary_df[summary_df["Задача"] == tid]
        if row.empty:
            continue
        row = row.iloc[0].to_dict()
        t_in = it_in[it_in["Задача"] == tid]
        work_days = _sum_interval_days(t_in, "Начало_ts", "Завершение_ts", work_start_h, work_end_h, net_ratio, net_day_hours)
        row[work_col] = round(work_days, 2)
        if iter_col:
            row[iter_col] = int(len(t_in))

        if role == "qa":
            queue_days = _sum_interval_days(wt_in[wt_in["Задача"] == tid], "Начало_ts", "Завершение_ts", work_start_h, work_end_h, net_ratio, net_day_hours)
            row[queue_col] = round(queue_days, 2)
            cycle_days = work_days + queue_days
            row[cycle_col] = round(cycle_days, 2)
            if other_col:
                row[other_col] = 0.0
            row[flow_col] = round(work_days / cycle_days * 100, 1) if cycle_days > 0 else 0.0
        elif role == "dev":
            rv_dev = rv_in[rv_in["Этап ревью"].isin(STATUS_DEV_REVIEW)]
            rev_days = _sum_interval_days(rv_dev[rv_dev["Задача"] == tid], "Начало_ts", "Завершение_ts", work_start_h, work_end_h, net_ratio, net_day_hours)
            rv_dev_wait = rv_in[(rv_in["Этап ревью"] == "К ревью (разработка)") & (rv_in["Задача"] == tid)]
            row[review_wait_col] = round(_sum_interval_days(rv_dev_wait, "Начало_ts", "Завершение_ts", work_start_h, work_end_h, net_ratio, net_day_hours), 2)
            wait_days = float(row.get(wait_col, 0.0) or 0.0)
            row[rev_col] = round(rev_days, 2)
            row[queue_col] = round(wait_days + rev_days, 2)
            row[cycle_col] = round(work_days + wait_days + rev_days, 2)
            row[flow_col] = round(work_days / (work_days + wait_days + rev_days) * 100, 1) if (work_days + wait_days + rev_days) > 0 else 0.0
        else:
            rv_an = rv_in[rv_in["Этап ревью"].isin(STATUS_ANALYTICS_REVIEW)]
            rev_days = _sum_interval_days(rv_an[rv_an["Задача"] == tid], "Начало_ts", "Завершение_ts", work_start_h, work_end_h, net_ratio, net_day_hours)
            rv_an_wait = rv_in[(rv_in["Этап ревью"] == "К ревью (аналитика)") & (rv_in["Задача"] == tid)]
            row[review_wait_col] = round(_sum_interval_days(rv_an_wait, "Начало_ts", "Завершение_ts", work_start_h, work_end_h, net_ratio, net_day_hours), 2)
            wait_days = float(row.get(wait_col, 0.0) or 0.0)
            row[rev_col] = round(rev_days, 2)
            row[queue_col] = round(wait_days + rev_days, 2)
            row[cycle_col] = round(work_days + wait_days + rev_days, 2)
            row[flow_col] = round(work_days / (work_days + wait_days + rev_days) * 100, 1) if (work_days + wait_days + rev_days) > 0 else 0.0

        result_rows.append(row)

    if not result_rows:
        return summary_df.iloc[0:0].copy()
    return pd.DataFrame(result_rows)
