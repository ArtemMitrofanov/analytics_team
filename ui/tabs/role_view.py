"""ui/tabs/role_view.py — Универсальный шаблон рендеринга аудита направления (QA/Dev/Analytics)."""
from typing import List, Optional
import pandas as pd
import streamlit as st
from utils.stats import calc_stats
from ui.components import render_searchable_log
from data.metrics import recompute_role_period_metrics


def _filter_by_period(df: Optional[pd.DataFrame], date_col: str, start_date, end_date) -> Optional[pd.DataFrame]:
    """Оставляет строки, чей интервал пересекается с [start_date, end_date]."""
    if df is None or df.empty or date_col not in df.columns:
        return df
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    d1 = pd.to_datetime(df["Начало"])
    d2 = pd.to_datetime(df["Завершение"])
    mask = (d1 < end_ts) & (d2 >= start_ts)
    return df[mask]


def _sum_rev_column(summary: pd.DataFrame, rev_col: str, role_key: str) -> pd.Series:
    """Для 'Весь период': сумма ревью-статусов роли (в днях)."""
    from config import STATUS_DEV_REVIEW, STATUS_ANALYTICS_REVIEW
    if role_key == "dev":
        cols = [f"{s} (д.)" for s in STATUS_DEV_REVIEW]
    elif role_key == "an":
        cols = [f"{s} (д.)" for s in STATUS_ANALYTICS_REVIEW]
    else:
        return pd.Series(0.0, index=summary.index)
    present = [c for c in cols if c in summary.columns]
    if not present:
        return pd.Series(0.0, index=summary.index)
    return summary[present].fillna(0).sum(axis=1).round(2)


def render_role_tab(
    role_title: str,
    work_status_col: str,
    queue_status_col: str,
    cycle_col: str,
    flow_col: str,
    table_cols: List[str],
    iter_df: pd.DataFrame,
    rev_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    actor_col_name: str,
    net_day_hours: float,
    reworks_df: pd.DataFrame = None,
    role_key: str = "qa",
    start_date=None,
    end_date=None,
    work_start_h: int = 9,
    work_end_h: int = 18,
    net_ratio: float = 0.78,
    wait_df: pd.DataFrame = None,
    wait_col: Optional[str] = None,
    rev_col: Optional[str] = None,
    global_summary_df: pd.DataFrame = None,
):
    period_active = start_date is not None and end_date is not None

    if period_active:
        iter_p = _filter_by_period(iter_df, "Начало", start_date, end_date)
        rev_p = _filter_by_period(rev_df, "Начало", start_date, end_date)
        if reworks_df is not None and not reworks_df.empty and "Дата возврата" in reworks_df.columns:
            rw = reworks_df.copy()
            rw["Дата возврата_ts"] = pd.to_datetime(rw["Дата возврата"])
            rw = rw[rw["Дата возврата_ts"].dt.normalize().between(pd.Timestamp(start_date), pd.Timestamp(end_date))]
            reworks_p = rw.drop(columns=["Дата возврата_ts"])
        else:
            reworks_p = reworks_df
        wait_p = _filter_by_period(wait_df, "Начало", start_date, end_date) if wait_df is not None and not wait_df.empty else wait_df
        summary_p = recompute_role_period_metrics(
            summary_df, iter_p, rev_p, role_key,
            start_date, end_date, work_start_h, work_end_h, net_ratio, net_day_hours,
            wait_df=wait_p,
        )
    else:
        iter_p, rev_p, reworks_p = iter_df, rev_df, reworks_df
        summary_p = summary_df.copy()
        if rev_col and rev_col not in summary_p.columns:
            summary_p[rev_col] = _sum_rev_column(summary_p, rev_col, role_key)

    st.subheader(f"Аудит направления: {role_title}")
    sub_tabs = st.tabs([
        f"📊 Метрики и Flow {role_title}",
        f"👥 Аналитика по сотрудникам",
        "🔍 Анализ Ревью / Доработок",
        f"📋 Журнал итераций",
    ])

    with sub_tabs[0]:
        act_df = summary_p[summary_p[work_status_col] > 0] if work_status_col in summary_p else summary_p
        w_m, w_med, w_p85, _ = calc_stats(act_df.get(work_status_col, pd.Series(dtype=float)))
        c_m, c_med, c_p85, _ = calc_stats(act_df.get(cycle_col, pd.Series(dtype=float)))
        f_m, f_med, f_p85, _ = calc_stats(act_df.get(flow_col, pd.Series(dtype=float)))

        if wait_col and rev_col:
            q1_m, q1_med, q1_p85, _ = calc_stats(act_df.get(wait_col, pd.Series(dtype=float)))
            q2_m, q2_med, q2_p85, _ = calc_stats(act_df.get(rev_col, pd.Series(dtype=float)))
            cols = st.columns(5)
            cols[0].metric("В работе", f"{w_m:.2f} д.", f"Мед: {w_med:.2f} | P85: {w_p85:.2f}")
            cols[1].metric("В очереди", f"{q1_m:.2f} д.", f"Мед: {q1_med:.2f} | P85: {q1_p85:.2f}", delta_color="inverse")
            cols[2].metric("Ревью", f"{q2_m:.2f} д.", f"Мед: {q2_med:.2f} | P85: {q2_p85:.2f}", delta_color="inverse")
            cols[3].metric("Цикл этапа", f"{c_m:.2f} д.", f"Мед: {c_med:.2f} | P85: {c_p85:.2f}")
            cols[4].metric("Flow этапа", f"{f_m:.1f}%", f"Мед: {f_med:.1f}% | P85: {f_p85:.1f}%")
        else:
            q_m, q_med, q_p85, _ = calc_stats(act_df.get(queue_status_col, pd.Series(dtype=float)))
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("В работе", f"{w_m:.2f} д.", f"Мед: {w_med:.2f} | P85: {w_p85:.2f}")
            c2.metric("Очередь / Ревью", f"{q_m:.2f} д.", f"Мед: {q_med:.2f} | P85: {q_p85:.2f}", delta_color="inverse")
            c3.metric("Цикл этапа", f"{c_m:.2f} д.", f"Мед: {c_med:.2f} | P85: {c_p85:.2f}")
            c4.metric("Flow этапа", f"{f_m:.1f}%", f"Мед: {f_med:.1f}% | P85: {f_p85:.1f}%")

        st.markdown("---")
        st.markdown("##### Сводная таблица по задачам (в днях)")
        if wait_col and rev_col and rev_col in summary_p.columns:
            table_cols_ext = list(table_cols)
            for extra in (wait_col, rev_col):
                if extra not in table_cols_ext:
                    table_cols_ext.append(extra)
        else:
            table_cols_ext = table_cols
        metric_cols = [c for c in table_cols_ext if c != "Задача" and c in summary_p.columns]
        table_filtered = summary_p[table_cols_ext][(summary_p[metric_cols] > 0).any(axis=1)]
        if not table_filtered.empty:
            st.dataframe(table_filtered, use_container_width=True, hide_index=True)
        else:
            st.info(f"В выбранном периоде нет активности по направлению {role_title}.")

        if period_active and global_summary_df is not None and "finished_at" in global_summary_df.columns:
            finished_dt = pd.to_datetime(global_summary_df["finished_at"], errors="coerce")
            start_ts = pd.Timestamp(start_date)
            end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            in_period = finished_dt.between(start_ts, end_ts)
            finished_in_period = global_summary_df[in_period]
            finished_with_work = finished_in_period[finished_in_period.get(work_status_col, 0) > 0]
            st.markdown("---")
            st.markdown(f"##### Завершённые в периоде задачи с работой {role_title} > 0")
            st.caption(f"Всего завершено в периоде: {len(finished_in_period)} | С работой {role_title} > 0: {len(finished_with_work)}")
            if not finished_with_work.empty:
                executor_map = {}
                if not iter_p.empty and actor_col_name in iter_p.columns:
                    executor_map = iter_p.groupby("Задача")[actor_col_name].apply(
                        lambda x: ", ".join(x.dropna().astype(str).unique())
                    ).to_dict()
                
                display_df = finished_with_work.copy()
                display_df["Исполнитель"] = display_df["Задача"].map(executor_map).fillna("")
                
                # Добавляем колонку с фактическим размером задачи для роли
                fact_col_map = {"qa": "qa_fact", "dev": "dev_fact", "an": "an_fact"}
                fact_col = fact_col_map.get(role_key)
                if fact_col and fact_col in display_df.columns:
                    display_df["Размер (факт)"] = display_df[fact_col]
                    size_col = "Размер (факт)"
                else:
                    size_col = None
                
                display_cols = ["Задача", "Исполнитель", "finished_at", work_status_col]
                if size_col:
                    display_cols.insert(3, size_col)
                if queue_status_col in display_df.columns:
                    display_cols.append(queue_status_col)
                if cycle_col in display_df.columns:
                    display_cols.append(cycle_col)
                if flow_col in display_df.columns:
                    display_cols.append(flow_col)
                display_cols = [c for c in display_cols if c in display_df.columns]
                st.dataframe(
                    display_df[display_cols].sort_values("finished_at"),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info(f"Нет завершённых в периоде задач с работой {role_title} > 0.")

    with sub_tabs[1]:
        if not iter_p.empty and actor_col_name in iter_p.columns:
            grp = iter_p.groupby(actor_col_name).agg(
                tasks=("Задача", "nunique"), iters=("Итерация", "count"), days=("Раб. дней", "sum")
            ).reset_index()
            grp["avg_per_task"] = (grp["days"] / grp["tasks"]).round(2)
            grp = grp.rename(columns={"tasks": "Задач (шт)", "iters": "Подходов (шт)", "days": "Суммарно (д.)", "avg_per_task": "Среднее на задачу (д.)"})
            st.dataframe(grp, use_container_width=True, hide_index=True)
        else:
            st.info("Нет данных по исполнителям.")

    with sub_tabs[2]:
        if reworks_p is not None and not reworks_p.empty:
            st.markdown("##### 🔧 Возвраты на доработку")
            st.dataframe(reworks_p, use_container_width=True, hide_index=True)
        elif not rev_p.empty:
            st.markdown("##### 🔍 Анализ задержек ревью")
            rev_summary = rev_p.groupby("Этап ревью").agg(
                tasks=("Задача", "nunique"), total_days=("Длительность (д.)", "sum"), avg_days=("Длительность (д.)", "mean")
            ).reset_index()
            st.dataframe(rev_summary, use_container_width=True, hide_index=True)
            st.markdown("###### Лог событий:")
            st.dataframe(rev_p, use_container_width=True, hide_index=True)
        else:
            st.info("Нет зафиксированных данных ревью/доработок.")

    with sub_tabs[3]:
        render_searchable_log(iter_p, "Задача", f"Журнал итераций {role_title}", f"{role_key}_iters.csv", f"log_{role_key}")
