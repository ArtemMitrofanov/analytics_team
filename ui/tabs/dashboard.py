"""ui/tabs/dashboard.py — Интерактивный дашборд месячных метрик и трендов."""
from __future__ import annotations

from dataclasses import replace
from html import escape
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
from ui.bento import (
    active_theme_mode,
    bento_palette,
    glass_panel_marker,
    render_hero,
    render_kpi_card,
    render_plotly,
    render_section_header,
)
from utils.forecast import ForecastResult, forecast_series

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


def _pct_change(current: float | None, previous: float | None) -> float | None:
    """Относительное изменение в процентах; None, если базы сравнения нет."""
    if current is None or previous is None:
        return None
    if abs(previous) < 1e-9:
        return None
    return (current - previous) / abs(previous) * 100.0


def _trend_direction(change_pct: float | None) -> str:
    if change_pct is None or abs(change_pct) < 0.05:
        return "flat"
    return "up" if change_pct > 0 else "down"


def _series_values(
    wide: pd.DataFrame,
    key: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    limit: int = 6,
) -> list[float]:
    subset = wide.loc[(wide.index >= start) & (wide.index <= end)]
    if key not in subset.columns:
        return []
    values = pd.to_numeric(subset[key], errors="coerce").dropna().tail(limit)
    return [float(value) for value in values]


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
        ("tasks_done", "Завершено задач", "normal", "check", "emerald"),
        ("lead_time_mean", "Lead Time, среднее", "inverse", "clock", "indigo"),
        ("queue_mean", "Очереди, среднее", "inverse", "layers", "violet"),
        ("flow_mean", "Сквозной Flow", "normal", "gauge", "cyan"),
    )
    cols = st.columns([1.3, 1, 1, 1], gap="medium")
    for col, (key, label, delta_color, icon, accent) in zip(cols, kpis):
        spec = get_metric_spec(key)
        value = _value_at(wide, last_month, key)
        previous = _value_at(wide, previous_month, key) if previous_month is not None else None
        change_pct = _pct_change(value, previous)
        trend = _trend_direction(change_pct)
        caption = (
            "к прошлому месяцу"
            if previous_month is not None
            else "нет базы сравнения"
        )
        with col:
            render_kpi_card(
                label,
                _fmt_value(spec, value),
                change_pct,
                trend,
                icon,
                positive_is_good=delta_color == "normal",
                caption=caption,
                accent=accent,
                sparkline_values=_series_values(wide, key, start, end),
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
    palette = bento_palette(active_theme_mode())
    line_color = palette["violet"]
    forecast_color = palette["indigo"]
    muted = palette["muted"]

    if spec.key == "tasks_done":
        fig.add_trace(
            go.Bar(
                x=x_actual,
                y=y_tasks,
                name="Завершено задач",
                marker_color="rgba(52, 211, 153, 0.58)",
                marker_line_width=0,
                hovertemplate="%{x}: %{y:.0f} задач<extra></extra>",
            )
        )
    else:
        fig.add_trace(
            go.Bar(
                x=x_actual,
                y=y_tasks,
                name="Завершено задач",
                marker_color="rgba(129, 140, 248, 0.22)",
                marker_line_width=0,
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
                line=dict(color=line_color, width=2.6),
                marker=dict(
                    size=7,
                    color=line_color,
                    line=dict(width=2, color=palette["text"]),
                ),
                fill="tozeroy",
                fillcolor="rgba(192, 132, 252, 0.10)",
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
                line=dict(color=forecast_color, width=2.2, dash="dash"),
                marker=dict(size=6, symbol="diamond", color=forecast_color),
                hovertemplate=f"%{{x}}: %{{y:.{spec.digits}f}} {spec.unit}<extra></extra>",
            )
        )
        if len(band_x) > 1:
            fig.add_trace(
                go.Scatter(
                    x=band_x + band_x[::-1],
                    y=band_upper + band_lower[::-1],
                    fill="toself",
                    fillcolor="rgba(52, 211, 153, 0.12)",
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
            font=dict(size=10, color=muted),
            yshift=8,
        )

    fig.update_layout(
        height=430,
        margin=dict(l=6, r=10, t=42, b=8),
        barmode="group",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(
            title=spec.unit,
            rangemode="tozero" if spec.lower is not None and spec.lower >= 0 else "normal",
            showgrid=True,
            gridcolor=palette["grid"],
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
    render_plotly(fig, key="dashboard_main_chart")

    return result


def _anomaly_note(series: pd.Series) -> tuple[str, bool]:
    """Оценить последнее значение относительно среднего (z-score)."""
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 4:
        return "мало данных", False
    std = values.std()
    if pd.isna(std) or std == 0:
        return "не обнаружено", False
    z_score = (values.iloc[-1] - values.mean()) / std
    if abs(z_score) >= 1.5:
        where = "выше нормы" if z_score > 0 else "ниже нормы"
        return f"{where} ({z_score:+.1f}σ)", True
    return "не обнаружено", False


def _render_signal_panel(
    wide: pd.DataFrame,
    spec: MetricSpec,
    start: pd.Timestamp,
    end: pd.Timestamp,
    horizon: int,
    result: ForecastResult,
) -> None:
    subset = wide.loc[(wide.index >= start) & (wide.index <= end)]
    series = subset.get(spec.key, pd.Series(dtype=float))
    anomaly_text, is_anomaly = _anomaly_note(series)
    has_partial = any(bool(value) for value in subset.get("is_partial", pd.Series(dtype=bool)))
    mtd_text = "есть MTD" if has_partial else "нет"

    if horizon <= 0:
        status, tone, value, value_label = "Прогноз отключён", "neutral", "—", "Горизонт 0 месяцев"
        footer = "Выберите горизонт прогноза, чтобы увидеть экстраполяцию тренда."
        trend_text = "—"
        quality_text = "—"
        mape_text = "—"
    elif result.available and result.points:
        point = result.points[0]
        status = _STATUS_LABELS.get(result.status, result.status)
        tone = {"improving": "good", "worsening": "bad"}.get(result.status, "neutral")
        value = _fmt_value(spec, point.value)
        value_label = f"Прогноз на {format_month(point.month)}"
        trend_text = f"{_TREND_ARROWS.get(result.trend, '')} {result.slope_pct:+.1f}% / мес."
        quality_text = _QUALITY_LABELS.get(result.quality, result.quality)
        mape_text = f"{result.backtest_mape:.1f}%" if result.backtest_mape is not None else "—"
        footer = (
            f"Метод: {escape(str(result.method))}. "
            "Статистическая экстраполяция, не обязательство."
        )
    else:
        status, tone, value = "Мало данных", "neutral", "—"
        value_label = "Прогноз недоступен"
        trend_text = "—"
        quality_text = "—"
        mape_text = "—"
        footer = (
            escape(str(result.reason).rstrip(".")) + "."
            if result.reason
            else "Для прогноза нужно минимум 4 полных месяца."
        )

    rows = [
        ("Тренд", trend_text, False),
        ("Качество backtest", quality_text, False),
        ("MAPE", mape_text, False),
        ("Аномалии", anomaly_text, is_anomaly),
        ("Текущий месяц", mtd_text, False),
    ]
    rows_html = "".join(
        '<div class="bento-panel__row">'
        f'<span class="bento-panel__key">{escape(str(key))}</span>'
        f'<span class="bento-panel__val{" bento-panel__val--warn" if warn else ""}">'
        f"{escape(str(value_text))}</span></div>"
        for key, value_text, warn in rows
    )

    st.markdown(
        '<div class="bento-panel">'
        '<div class="bento-panel__head"><div>'
        '<span class="bento-eyebrow">Signal</span>'
        '<div class="bento-panel__title">Прогноз и качество</div>'
        "</div>"
        f'<span class="bento-status bento-status--{tone}">'
        f'<span class="bento-dot"></span>{escape(str(status))}</span>'
        "</div>"
        f'<div class="bento-signal__value">{escape(str(value))}</div>'
        f'<div class="bento-signal__label">{escape(str(value_label))}</div>'
        f'<div class="bento-panel__rows">{rows_html}</div>'
        f'<div class="bento-panel__foot">{footer}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


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

    render_hero(
        "Дашборд команды",
        "Динамика Lead Time, очередей и Flow Efficiency по месяцам. Текущий месяц "
        "показан как MTD и не участвует в прогнозе: прогноз — статистическая "
        "экстраполяция тренда, а не обязательство.",
        eyebrow="Process intelligence",
        chips=("Lead Time", "Flow Efficiency", "Throughput", "Forecast", "Anomaly watch"),
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

    with st.container():
        glass_panel_marker()
        render_section_header(
            "Срез данных",
            "Период, горизонт прогноза и группа метрик.",
            eyebrow="Controls",
        )
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(
            [1.25, 1.25, 1.2, 1.5],
            gap="medium",
        )
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

        metric_col, info_col = st.columns([1.25, 2.75], gap="medium")
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
            partial_months = [
                month
                for month in wide.index
                if start <= month <= end and bool(wide.loc[month, "is_partial"])
            ]
            if partial_months:
                st.caption(
                    f"**{format_month(partial_months[-1])} — MTD:** месяц ещё не завершён, "
                    "в тренд и прогноз не включается."
                )
            elif horizon > 0:
                st.caption(
                    "Для прогноза нужно минимум 4 полных месяца. "
                    "Если точек меньше, будет показан только фактический тренд."
                )

    _render_kpis(wide, start, end)

    chart_title = (
        "Объём завершённых задач"
        if selected_spec.key == "tasks_done"
        else f"{selected_spec.label} и объём задач"
    )
    chart_col, signal_col = st.columns([2.15, 1], gap="medium")
    with chart_col:
        with st.container():
            glass_panel_marker()
            render_section_header(
                chart_title,
                "Фактические значения, MTD и статистический прогноз.",
                eyebrow="Trend",
            )
            result = _render_main_chart(wide, selected_spec, start, end, horizon)
    with signal_col:
        _render_signal_panel(wide, selected_spec, start, end, horizon, result)

    with st.container():
        glass_panel_marker()
        render_section_header(
            "Прогноз по метрикам",
            "Экстраполяция по выбранной группе метрик и качество backtest.",
            eyebrow="Forecast",
        )
        _render_forecast_table(wide, specs, start, end, horizon)

    with st.container():
        glass_panel_marker()
        render_section_header(
            "Помесячный срез",
            "Полная таблица значений и размер выборки по каждой метрике.",
            eyebrow="Monthly",
        )
        _render_monthly_table(wide, specs, start, end)

    with st.container():
        glass_panel_marker()
        render_section_header(
            "Детализация",
            "Задачи, завершённые в выбранном месяце, и экспорт в CSV.",
            eyebrow="Drilldown",
        )
        _render_drilldown(summary_df, wide, start, end)
