"""Помесячный график очереди перед QA и проверяемая дневная детализация."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.qa_queue import (
    build_queue_daily, build_queue_monthly, local_timestamp, task_texts, matching_task_ids,
)
from config import MONTH_NAMES_RU


def render_qa_queue(events, start_date=None, end_date=None):
    st.markdown("##### Среднее количество задач в очереди «К тестированию»")
    st.caption("За день считаем уникальные задачи, ожидавшие QA хотя бы часть суток "
               "00:00–24:00. Среднее за месяц — сумма дневных значений / число "
               "учтённых рабочих дней РФ, включая дни с нулевой очередью.")
    if events is None or events.empty:
        st.info("Нет истории статусов для расчёта очереди.")
        return
    texts = task_texts(events)
    options = sorted(texts.index)
    def task_label(task_id):
        title = texts.at[task_id, "title"]
        return f"{task_id} — {title[:100]}" if title else task_id

    with st.sidebar:
        st.markdown("---")
        st.subheader("Фильтр очереди QA")
        mode = st.radio("Задачи на графике", ["Без сторонних задач", "Все задачи"],
                        key="qa_queue_filter_mode")
        filtering = mode == "Без сторонних задач"
        words = st.text_area("Исключать слова в названии или описании", value="УУ\nПД\nУС",
                             help="Одно слово или фраза на строку. Совпадение целиком, без учёта регистра.",
                             key="qa_queue_keywords", disabled=not filtering)
        manual = st.multiselect("Дополнительно исключить задачи", options, format_func=task_label,
                                key="qa_queue_manual_exclude", disabled=not filtering)
        keep = st.multiselect("Всегда учитывать задачи", options, format_func=task_label,
                              help="Имеет приоритет над словами и ручным исключением.",
                              key="qa_queue_manual_keep", disabled=not filtering)
        st.caption("Фильтр влияет только на график очереди QA и его дневную детализацию. "
                   "Настройки действуют в текущей сессии.")
    automatic = matching_task_ids(texts, words.splitlines())
    excluded = (automatic | set(manual)) - set(keep) if filtering else set()
    st.caption(f"Режим: {mode.lower()} · Исключено задач: {len(excluded)} из {len(texts)}.")
    missing = int((~texts["has_text"]).sum())
    if filtering and missing:
        st.caption(f"Без названия и описания в выгрузке: {missing} задач. Они остаются в расчёте; "
                   "при необходимости исключите их вручную в левой панели.")
    if excluded:
        with st.expander("Исключённые задачи"):
            excluded_table = texts.loc[sorted(excluded), ["title"]].reset_index().rename(
                columns={"task_id": "Задача", "title": "Название"})
            excluded_table["Причина"] = ["По словам" if tid in automatic else "Вручную"
                                         for tid in sorted(excluded)]
            st.dataframe(excluded_table, use_container_width=True, hide_index=True)
    with st.expander("Период полноты данных и методика"):
        timezone = st.selectbox("Часовой пояс команды", ["Asia/Yekaterinburg", "Europe/Moscow"],
                               key="qa_queue_timezone")
        now = local_timestamp(pd.Timestamp.now(tz=timezone), timezone)
        timestamps = events["timestamp"].dropna().map(lambda x: local_timestamp(x, timezone))
        latest = timestamps.max()
        default = min(latest.normalize() - pd.Timedelta(days=1), now.normalize() - pd.Timedelta(days=1))
        complete = st.date_input("История полна по дату (включительно)", value=default.date(),
                                max_value=(now.normalize() - pd.Timedelta(days=1)).date(),
                                key="qa_queue_complete_through")
        st.caption(f"Последнее событие: {latest:%d.%m.%Y %H:%M}. По умолчанию взяты сутки "
                   "до даты последнего события. Это ориентир, а не подтверждение полноты: "
                   "укажите дату, по которую выгружена вся история всех задач. "
                   "Даты без часового пояса считаются локальным временем команды.")
        st.caption("Сегодня и будущие дни исключены. Незавершённые задачи и очередь из прошлых "
                   "месяцев включены; повторные входы за день считаются один раз. "
                   "Расчёт начинается с первого дня доступной истории; предполагается, что "
                   "история переходов задач полная. Фильтр периода ограничивает дни, а не задачи. "
                   "Сокращённые рабочие дни также считаются полными сутками.")
        st.markdown("Календарь РФ: [XMLCalendar, 2013–2026](https://github.com/xmlcalendar/data); "
                    "[производственный календарь 2026](https://www.consultant.ru/law/ref/calendar/proizvodstvennye/2026/).")
    try:
        daily = build_queue_daily(events, complete, start_date, end_date, now, timezone,
                                  excluded_task_ids=excluded)
    except ValueError as exc:
        st.warning(str(exc))
        return
    monthly = build_queue_monthly(daily)
    if monthly.empty:
        st.info("В выбранном периоде нет полных рабочих дней с доступной историей.")
        return
    labels = [f"{MONTH_NAMES_RU[m.month]} {m.year}" for m in monthly["month"]]
    fig = go.Figure(go.Bar(
        x=labels, y=monthly["average"], text=monthly["average"].map(lambda x: f"{x:.1f}"),
        textposition="outside", marker_color="#818CF8", customdata=monthly[["workdays"]].to_numpy(),
        hovertemplate="%{x}<br>Среднее: %{y:.2f} задачи<br>Учтено рабочих дней: %{customdata[0]}<extra></extra>",
    ))
    fig.update_layout(xaxis_title="Месяц", yaxis_title="Задач в среднем за рабочий день",
                      yaxis_range=[0, max(1.0, monthly["average"].max() * 1.2)],
                      margin=dict(t=25, b=25), height=350)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Учтено рабочих дней: {len(daily)} · Последний учтённый день: "
               f"{daily['date'].max():%d.%m.%Y} · Неполные месяцы рассчитаны только по учтённым дням.")
    with st.expander("Количество задач по дням"):
        display = daily.rename(columns={"date": "Дата", "tasks": "Задач в очереди"}).copy()
        display["Дата"] = display["Дата"].dt.date
        st.dataframe(display, use_container_width=True, hide_index=True)
        st.download_button("Скачать дневные значения CSV", display.to_csv(index=False).encode("utf-8-sig"),
                           "qa_queue_daily.csv", "text/csv", key="qa_queue_download")
