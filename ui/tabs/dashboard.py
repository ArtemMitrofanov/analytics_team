"""ui/tabs/dashboard.py — Интерактивный дашборд месячных метрик и трендов."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.monthly_metrics import (
    CORE_GROUP,
    METRIC_GROUP_LABELS,
    MetricSpec,
    build_monthly_metrics,
    format_month,
    get_metric_spec,
    get_metric_specs,
    pivot_monthly_metrics,
)
from utils.forecast import ForecastResult, forecast_series

_BLUE = "#2291FF"
_DARK_BLUE = "#153177"
_MUTED = "rgba(34, 34, 34, 0.55)"

_QUALITY_LABELS = {
    "high": "высокое",
    "medium": "среднее",
    "low": "низкое",
    "unavailable": "—",
}
_STATUS_LABELS = {
    "improving": "улучшается",
    "worsening": "ухудшается",
    "stable": "стабильно",
    "changing": "меняется",
}
_TREND_ARROWS = {"up": "↑", "down": "↓", "flat": "→"}


def _fmt_value(spec: MetricSpec, value: Any) -> str:
    if value is None or pd.isna(value):
        return "—"
    value = float(value)
    if spec.unit == "%":
        return f"{value:.{spec.digits}f}%"
    if spec.unit == "шт.":
        return f"{value:,.0f}".replace(",", " ")
    return f"{value:,.{spec.digits}f} {spec.unit}".replace(",", " ")


def _fmt_delta(value: float | None, unit: str) -> str | None:
    if value is None or pd.isna(value):
        return None
    sign = "+" if value > 0 else ""
    if unit == "%":
        return f"{sign}{value:.1f} п.п."
    if unit == "шт.":
        return f"{sign}{value:.0f}"
    return f"{sign}{value:.2f} д."


def _value_at(wide: pd.DataFrame, month: pd.Timestamp, key: str) -> float | None:
    if month not in wide.index or key not in wide.columns:
        return None
    value = wide.loc[month, key]
    if pd.isna(value):
        return None
    return float(value)


def _forecast_for(
    wide: pd.DataFrame,
    spec: MetricSpec,
    start: pd.Timestamp,
    end: pd.Timestamp,
    horizon: int,
) -> ForecastResult:
    """Прогноз по выбранному диапазону; текущий неполный месяц не участвует в fit."""
    subset = wide.loc[(wide.index >= start) & (wide.index <= end)]
    if subset.empty or spec.key not in subset.columns:
        return forecast_series(pd.Series(dtype=float), horizon=0)

    complete_mask = (~subset["is_partial"].astype(bool)) & subset["has_data"].astype(bool)
    complete = subset.loc[complete_mask, spec.key].dropna()
    if horizon <= 0:
        return forecast_series(
            complete,
            horizon=0,
            direction=spec.direction,
            lower=spec.lower,
            upper=spec.upper,
        )

    last_visible = subset.index.max()
    has_partial = bool(subset["is_partial"].iloc[-1])
    request_horizon = horizon + (1 if has_partial else 0)
    result = forecast_series(
        complete,
        horizon=request_horizon,
        direction=spec.direction,
        lower=spec.lower,
        upper=spec.upper,
        max_horizon=request_horizon,
    )

    if has_partial and result.points:
        points = tuple(point for point in result.points if point.month > last_visible)[:horizon]
        result = replace(result, points=points)
    return result


def _render_kpis(wide: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> None:
    subset = wide.loc[(wide.index >= start) & (wide.index <= end)]
    complete_months = [
        month
        for month in subset.index
        if not bool(subset.loc[month, "is_partial"]) and bool(subset.loc[month, "has_data"])
    ]
    if not complete_months:
        return

    last_month = max(complete_months)
    previous_month = max((month for month in complete_months if month < last_month), default=None)

    kpis = (
        ("tasks_done", "Завершено задач", "normal"),
        ("lead_time_mean", "Lead Time, среднее", "inverse"),
        ("queue_mean", "Очереди, среднее", "inverse"),
        ("flow_mean", "Сквозной Flow", "normal"),
    )
    cols_row1 = st.columns(2)
    cols_row2 = st.columns(2)
    for col, (key, label, delta_color) in zip(
        [*cols_row1, *cols_row2], kpis
    ):
        spec = get_metric_spec(key)
        value = _value_at(wide, last_month, key)
        delta = None
        if previous_month is not None:
            prev = _value_at(wide, previous_month, key)
            if value is not None and prev is not None:
                delta = value - prev

        with col:
            st.metric(
                label=label,
                value=_fmt_value(spec, value),
                delta=_fmt_delta(delta, spec.unit),
                delta_color=delta_color,
            )

    caption = f"Последний полный месяц: **{format_month(last_month)}**"
    if previous_month is not None:
        caption += f", сравнение с **{format_month(previous_month)}**"
    st.caption(caption)


def _render_main_chart(
    wide: pd.DataFrame,
    spec: MetricSpec,
    start: pd.Timestamp,
    end: pd.Timestamp,
    horizon: int,
) -> ForecastResult:
    subset = wide.loc[(wide.index >= start) & (wide.index <= end)]
    if subset.empty:
        st.info("В выбранном диапазоне нет месяцев.")
        return forecast_series(pd.Series(dtype=float), horizon=0)

    x_actual = [format_month(month) for month in subset.index]
    y_metric = [
        None if pd.isna(value) else float(value)
        for value in subset.get(spec.key, pd.Series(index=subset.index, dtype=float))
    ]
    y_tasks = [
        None if pd.isna(value) else float(value)
        for value in subset.get("tasks_done", pd.Series(index=subset.index, dtype=float))
    ]

    result = _forecast_for(wide, spec, start, end, horizon)
    partial_months = [format_month(month) for month in subset.index if bool(subset.loc[month, "is_partial"])]

    fc_x: list[str] = []
    fc_y: list[float] = []
    band_x: list[str] = []
    band_lower: list[float] = []
    band_upper: list[float] = []

    if result.available and result.points:
        last_visible_value = y_metric[-1]
        if last_visible_value is not None:
            fc_x.append(x_actual[-1])
            fc_y.append(float(last_visible_value))
            band_x.append(x_actual[-1])
            band_lower.append(float(last_visible_value))
            band_upper.append(float(last_visible_value))

        for point in result.points:
            label = format_month(point.month)
            fc_x.append(label)
            fc_y.append(float(point.value))
            band_x.append(label)
            band_lower.append(float(point.lower))
            band_upper.append(float(point.upper))

    fig = go.Figure()

    if spec.key == "tasks_done":
        fig.add_trace(
            go.Bar(
                x=x_actual,
                y=y_tasks,
                name="Завершено задач",
                marker_color="rgba(34, 145, 255, 0.40)",
                hovertemplate="%{x}: %{y:.0f} задач<extra></extra>",
            )
        )
    else:
        fig.add_trace(
            go.Bar(
                x=x_actual,
                y=y_tasks,
                name="Завершено задач",
                marker_color="rgba(34, 145, 255, 0.30)",
                yaxis="y2",
                hovertemplate="%{x}: %{y:.0f} задач<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x_actual,
                y=y_metric,
                name=spec.label,
                mode="lines+markers",
                line=dict(color=_DARK_BLUE, width=2.4),
                marker=dict(size=7),
                connectgaps=False,
                hovertemplate=f"%{{x}}: %{{y:.{spec.digits}f}} {spec.unit}<extra></extra>",
            )
        )

    if fc_x:
        fig.add_trace(
            go.Scatter(
                x=fc_x,
                y=fc_y,
                name="Прогноз",
                mode="lines+markers",
                line=dict(color=_BLUE, width=2.2, dash="dash"),
                marker=dict(size=6, symbol="diamond"),
                hovertemplate=f"%{{x}}: %{{y:.{spec.digits}f}} {spec.unit}<extra></extra>",
            )
        )
        if len(band_x) > 1:
            fig.add_trace(
                go.Scatter(
                    x=band_x + band_x[::-1],
                    y=band_upper + band_lower[::-1],
                    fill="toself",
                    fillcolor="rgba(34, 145, 255, 0.14)",
                    line=dict(width=0),
                    mode="lines",
                    hoverinfo="skip",
                    showlegend=False,
                    name="Интервал прогноза",
                )
            )

    for label in partial_months:
        fig.add_annotation(
            x=label,
            y=1,
            yref="paper",
            text="MTD",
            showarrow=False,
            font=dict(size=10, color=_MUTED),
            yshift=8,
        )

    fig.update_layout(
        title=dict(
            text=f"{spec.label} и объём завершённых задач",
            font=dict(size=16),
            yref="container",
            y=1,
            yanchor="top",
            automargin=False,
            pad=dict(t=12),
        ),
        height=430,
        margin=dict(l=10, r=10, t=90, b=10),
        barmode="group",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(
            title=spec.unit,
            rangemode="tozero" if spec.lower is not None and spec.lower >= 0 else "normal",
            showgrid=True,
            gridcolor="rgba(34, 34, 34, 0.06)",
        ),
        yaxis2=dict(
            title="Задач",
            overlaying="y",
            side="right",
            showgrid=False,
            rangemode="tozero",
            visible=spec.key != "tasks_done",
        ),
        xaxis=dict(type="category", tickangle=-30),
    )
    st.plotly_chart(fig, use_container_width=True, key="dashboard_main_chart")

    if result.available and result.points:
        quality = _QUALITY_LABELS.get(result.quality, result.quality)
        caption = (
            f"Прогноз: **{_STATUS_LABELS.get(result.status, result.status)}**, "
            f"≈{result.slope_pct:+.1f}% в месяц. "
            f"Метод: {result.method}, качество backtest: **{quality}**."
        )
        if result.backtest_mape is not None:
            caption += f" MAPE: {result.backtest_mape:.1f}%."
        st.caption(caption)
    elif horizon > 0:
        st.caption(f"Прогноз недоступен: {result.reason.lower()}.")
    else:
        st.caption("Прогноз отключён: выбран горизонт 0 месяцев.")

    return result


def _render_forecast_table(
    wide: pd.DataFrame,
    specs: tuple[MetricSpec, ...],
    start: pd.Timestamp,
    end: pd.Timestamp,
    horizon: int,
) -> None:
    subset = wide.loc[(wide.index >= start) & (wide.index <= end)]
    complete_months = [
        month
        for month in subset.index
        if not bool(subset.loc[month, "is_partial"]) and bool(subset.loc[month, "has_data"])
    ]
    if not complete_months:
        return

    last_complete = max(complete_months)
    rows: list[dict[str, Any]] = []
    for spec in specs:
        last_value = _value_at(wide, last_complete, spec.key)
        result = _forecast_for(wide, spec, start, end, horizon)
        row: dict[str, Any] = {
            "Метрика": spec.label,
            "Последний полный месяц": _fmt_value(spec, last_value),
        }
        for index, point in enumerate(result.points, start=1):
            row[f"+{index} мес."] = _fmt_value(spec, point.value)
        row["Тренд"] = (
            f"{_TREND_ARROWS.get(result.trend, '')} "
            f"{_STATUS_LABELS.get(result.status, result.status)} "
            f"({result.slope_pct:+.1f}%/мес.)"
            if result.available
            else "—"
        )
        row["Качество"] = _QUALITY_LABELS.get(result.quality, result.quality)
        row["MAPE"] = f"{result.backtest_mape:.1f}%" if result.backtest_mape is not None else "—"
        rows.append(row)

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_monthly_table(
    wide: pd.DataFrame,
    specs: tuple[MetricSpec, ...],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    subset = wide.loc[(wide.index >= start) & (wide.index <= end)].sort_index(ascending=False)
    if subset.empty:
        return

    rows: list[dict[str, Any]] = []
    for month, row_data in subset.iterrows():
        row: dict[str, Any] = {"Месяц": format_month(month)}
        if bool(row_data.get("is_partial", False)):
            row["Месяц"] += " (MTD)"
        if not bool(row_data.get("has_data", True)):
            row["Месяц"] += " · нет данных"
        row["Задач завершено"] = _fmt_value(get_metric_spec("tasks_done"), row_data.get("tasks_done"))
        for spec in specs:
            if spec.key == "tasks_done":
                continue
            row[spec.label] = _fmt_value(spec, row_data.get(spec.key))
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("Показать размер выборки (n) по метрикам"):
        long_rows: list[dict[str, Any]] = []
        for month, row_data in subset.iterrows():
            for spec in specs:
                long_rows.append(
                    {
                        "Месяц": format_month(month),
                        "Метрика": spec.label,
                        "Значение": _fmt_value(spec, row_data.get(spec.key)),
                        "n": int(row_data.get(f"{spec.key}__n", 0)) if f"{spec.key}__n" in row_data else "—",
                    }
                )
        st.dataframe(pd.DataFrame(long_rows), use_container_width=True, hide_index=True)


def _render_drilldown(
    summary_df: pd.DataFrame,
    wide: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    months = [month for month in wide.index if start <= month <= end]
    if not months:
        return

    labels = {format_month(month): month for month in months}
    selected_label = st.selectbox(
        "Детализация по месяцу",
        options=list(labels.keys())[::-1],
        key="dashboard_detail_month",
    )
    selected_month = labels[selected_label]

    if "finished_at" not in summary_df.columns:
        st.info("Нет данных о завершении задач.")
        return

    finished = pd.to_datetime(summary_df["finished_at"], errors="coerce")
    detail = summary_df[finished.dt.to_period("M") == selected_month.to_period("M")].copy()
    if detail.empty:
        st.info(f"В {selected_label.lower()} нет завершённых задач.")
        return

    preferred_columns = [
        "Задача",
        "Полный Lead Time (д.)",
        "Всего очередей (д.)",
        "Чистая работа (д.)",
        "Сквозной Flow Efficiency (%)",
        "Циклтайм QA (дни)",
        "Цикл Разработки (д.)",
        "Цикл Аналитики (д.)",
        "Тип задачи",
        "Приоритет",
        "sla_status",
    ]
    columns = [column for column in preferred_columns if column in detail.columns]
    st.dataframe(detail[columns], use_container_width=True, hide_index=True)

    csv_data = detail[columns].to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 Скачать задачи месяца (CSV)",
        data=csv_data,
        file_name=f"dashboard_{selected_month.strftime('%Y_%m')}.csv",
        mime="text/csv",
        key="dashboard_detail_csv",
    )


def render_dashboard_tab(
    summary_df: pd.DataFrame,
    full_raw_df: pd.DataFrame | None = None,
    today: Any | None = None,
) -> None:
    """Отрисовать вкладку «Дашборд» (админская, общекомандные данные)."""
    try:
        role = st.session_state.get("user_role")
    except Exception:
        role = None
    if role not in (None, "admin"):
        st.warning("Дашборд доступен только администратору.")
        return

    st.subheader("📈 Дашборд: динамика метрик по месяцам")
    st.caption(
        "Задачи относятся к месяцу завершения. Текущий месяц показан как MTD "
        "и не участвует в расчёте прогноза. Прогноз — статистическая экстраполяция "
        "тренда, а не обязательство."
    )

    if summary_df is None or summary_df.empty:
        st.info("Нет завершённых задач для построения дашборда.")
        return

    data_months = None
    if full_raw_df is not None and not full_raw_df.empty and "timestamp" in full_raw_df.columns:
        data_months = pd.to_datetime(full_raw_df["timestamp"], errors="coerce").dt.to_period("M")

    monthly = build_monthly_metrics(summary_df, data_months=data_months, today=today)
    if monthly.empty:
        st.info("Нет завершённых задач для построения дашборда.")
        return

    wide = pivot_monthly_metrics(monthly)
    all_months = list(wide.index)
    if not all_months:
        st.info("Нет данных для построения дашборда.")
        return

    month_labels = [format_month(month) for month in all_months]
    month_by_label = dict(zip(month_labels, all_months))

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1.4, 1.4, 1.2, 1.6])
    with filter_col1:
        start_label = st.selectbox(
            "С месяца",
            options=month_labels,
            index=0,
            key="dashboard_start_month",
        )
    with filter_col2:
        end_label = st.selectbox(
            "По месяц",
            options=month_labels,
            index=len(month_labels) - 1,
            key="dashboard_end_month",
        )
    start = month_by_label[start_label]
    end = month_by_label[end_label]
    if start > end:
        start, end = end, start

    with filter_col3:
        horizon = st.select_slider(
            "Горизонт прогноза",
            options=[0, 1, 2, 3, 4, 5, 6],
            value=3,
            key="dashboard_horizon",
        )

    with filter_col4:
        group_label = st.selectbox(
            "Группа метрик",
            options=list(METRIC_GROUP_LABELS.values()),
            index=0,
            key="dashboard_group",
        )
    group = next(key for key, value in METRIC_GROUP_LABELS.items() if value == group_label)
    specs = get_metric_specs(group)

    metric_col, info_col = st.columns([2.2, 2.8])
    with metric_col:
        metric_labels = [spec.label for spec in specs]
        default_metric_index = 0
        if group != CORE_GROUP:
            default_metric_index = next(
                (index for index, spec in enumerate(specs) if spec.key.endswith("_cycle_mean")),
                0,
            )
        selected_metric_label = st.selectbox(
            "Метрика на графике",
            options=metric_labels,
            index=default_metric_index,
            key=f"dashboard_metric_{group}",
        )
    selected_spec = next(spec for spec in specs if spec.label == selected_metric_label)

    with info_col:
        partial_months = [month for month in wide.index if start <= month <= end and bool(wide.loc[month, "is_partial"])]
        if partial_months:
            st.info(
                f"{format_month(partial_months[-1])} — MTD: месяц ещё не завершён, "
                "в тренд и прогноз не включается."
            )
        elif horizon > 0:
            st.caption(
                "Для прогноза нужно минимум 4 полных месяца. "
                "Если точек меньше, будет показан только фактический тренд."
            )

    _render_kpis(wide, start, end)
    st.markdown("---")
    _render_main_chart(wide, selected_spec, start, end, horizon)

    st.markdown("---")
    st.markdown("#### Прогноз по метрикам")
    _render_forecast_table(wide, specs, start, end, horizon)

    st.markdown("---")
    st.markdown("#### Помесячный срез")
    _render_monthly_table(wide, specs, start, end)

    st.markdown("---")
    st.markdown("#### Детализация")
    _render_drilldown(summary_df, wide, start, end)
