"""Общий срез и помесячная динамика по выбранным командам."""
from collections.abc import Callable
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from data.team_comparison import (
    COUNT_METRIC,
    ESTIMATE_METRIC,
    METRICS,
    comparison_values,
    completed_in_period,
)
from data.workflow import READY_AT
from ui.bento import render_plotly


def render_team_comparison(
    teams: dict[str, str],
    get_stats: Callable[[str], dict],
    get_summary: Callable[[str], pd.DataFrame],
    get_months: Callable[[str], list[date]],
) -> None:
    st.subheader("Сравнение команд")
    selected = st.multiselect(
        "Команды", list(teams), default=list(teams), format_func=teams.__getitem__
    )
    if not selected:
        st.info("Выберите команды для сравнения.")
        return

    stats = {team_id: get_stats(team_id) for team_id in selected}
    with_data = [item for item in stats.values() if item["earliest_event"] is not None]
    if not with_data:
        st.info("Загрузите журнал задач хотя бы для одной команды.")
        return

    first = min(item["earliest_event"].date() for item in with_data)
    last = max(item["latest_event"].date() for item in with_data)
    period = st.date_input(
        "Период готовности к релизу", (first, last), min_value=first, max_value=last,
        key=f"comparison_period_{first}_{last}",
    )
    if len(period) != 2:
        st.info("Выберите начало и конец периода.")
        return
    start, end = period
    st.caption(
        "Время указано в рабочих днях по единому графику 09:00–18:00 с вычетом 2 часов. "
        "Готовность к релизу — первый переход в «К релизу». Для Бюджетирования "
        "также учитываются «Протестировано (к релизу)» и «Готово к переносу (релиз)». "
        "Для МСФО учитываются выход из «Протестировано» без возврата в разработку "
        "и прямой переход из «В тестировании» в «Сдача-Приёмка» или «Завершено». "
        "Lead Time — от первого входа в «К аналитике» или «В аналитике» до готовности к релизу. "
        "Cycle Time — от первого активного этапа до готовности к релизу. "
        "Шкала средней оценки: XS=1, S=2, M=3, L=4, XL=5."
    )

    table_rows = []
    count_rows = []
    completed = {}
    coverage = {}
    period_months = pd.period_range(start, end, freq="M")
    for team_id in selected:
        summary = get_summary(team_id) if stats[team_id]["total_rows"] else pd.DataFrame()
        completed[team_id] = completed_in_period(summary, start, end)
        coverage[team_id] = {pd.Period(month, freq="M") for month in get_months(team_id)}
        values = comparison_values(completed[team_id])
        row = {metric: value for metric, (value, _) in values.items()}
        if not coverage[team_id].intersection(period_months) and completed[team_id].empty:
            row[COUNT_METRIC] = None
        table_rows.append({"Команда": teams[team_id], **row})
        count_rows.append({
            "Команда": teams[team_id], **{metric: n for metric, (_, n) in values.items()}
        })

    formats = {
        metric: st.column_config.NumberColumn(format="%d" if metric == COUNT_METRIC else "%.2f")
        for metric in METRICS
    }
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True, column_config=formats)
    with st.expander("Количество задач в расчёте"):
        st.dataframe(pd.DataFrame(count_rows), use_container_width=True, hide_index=True)

    metric = st.selectbox("Метрика на графике", METRICS)
    rows = []
    for team_id, tasks in completed.items():
        by_month = (
            {month: group for month, group in tasks.groupby(tasks[READY_AT].dt.to_period("M"))}
            if not tasks.empty else {}
        )
        for month in period_months:
            if month in by_month or (metric == COUNT_METRIC and month in coverage[team_id]):
                value, n = comparison_values(
                    by_month.get(month, pd.DataFrame())
                )[metric]
            else:
                value, n = None, 0
            rows.append({
                "Месяц": month.start_time, "Команда": teams[team_id], "Значение": value, "Задач": n,
            })

    if not rows or not any(pd.notna(row["Значение"]) for row in rows):
        st.info("За выбранный период нет значений для графика.")
        return
    unit = {
        COUNT_METRIC: "шт.",
        ESTIMATE_METRIC: "баллы шкалы",
    }.get(metric, "раб. дни")
    figure = px.line(
        pd.DataFrame(rows), x="Месяц", y="Значение", color="Команда", markers=True,
        hover_data=["Задач"], labels={"Значение": unit},
    )
    render_plotly(figure, key="team_comparison_chart", height=430)
