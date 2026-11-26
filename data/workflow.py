"""Статусы Finance и единица измерения сквозных метрик сравнения."""
import pandas as pd

FINANCE_PROJECT = "Finance"
READY_STATUS = "К релизу"
BUDGET_PROJECTS = {"KBABudg", "KBA-Budg"}
BUDGET_READY_STATUSES = ("Протестировано (к релизу)", "Готово к переносу (релиз)")
READY_AT = "ready_for_release_at"
RELEASED_AT = "released_at"
RELEASE_WAIT = "Ожидание релиза (д.)"
READY_LEAD = "Lead Time до готовности к релизу (д.)"
READY_CYCLE = "Cycle Time до готовности к релизу (д.)"
READY_STAGE_COLUMNS = {
    "В аналитике": "Аналитика до готовности к релизу (д.)",
    "В разработке": "Разработка до готовности к релизу (д.)",
    "В тестировании": "Тестирование до готовности к релизу (д.)",
}

FINANCE_STATUS_MAP = {
    "бэклог": "Бэклог",
    "бэклог на квартал": "Бэклог на квартал",
    "посмотреть на летучке": "Посмотреть на летучке",
    "к аналитике": "К аналитике",
    "в работе (аналитика)": "В аналитике",
    "к ревью (аналитика)": "К ревью (аналитика)",
    "в работе (ревью аналитика)": "Ревью аналитики",
    "в работе (ревью аналитики)": "Ревью аналитики",
    "готово к презентации": "Готово к презентации",
    "к проектированию": "К проектированию",
    "проектирование в работе": "Проектирование в работе",
    "ревью проектирование": "К ревью проектирования",
    "к ревью проектирование": "К ревью проектирования",
    "в работе ревью проектирование": "Ревью проектирования",
    "в работе ревью проектир-е": "Ревью проектирования",
    "к разработке": "К разработке",
    "в работе (разработка)": "В разработке",
    "к ревью": "К ревью (разработка)",
    "в работе (код-ревью)": "Код ревью",
    "в работе (код ревью)": "Код ревью",
    "к тестированию": "К тестированию",
    "в работе (тестирование)": "В тестировании",
    "ожидание": "Ожидание",
    "к релизу": READY_STATUS,
    "зарелизили": "Зарелизили",
}
FINANCE_EXTRA_STATUSES = (
    "Бэклог", "Бэклог на квартал", "Посмотреть на летучке", "Готово к презентации",
    "К проектированию", "Проектирование в работе", "К ревью проектирования",
    "Ревью проектирования", "Ожидание", READY_STATUS,
)
FINANCE_ACTIVE_STATUSES = ("Проектирование в работе", "Ревью проектирования")
STANDARD_STATUS_FIELDS = ("Текущий статус", "State")


def status_event_mask(events: pd.DataFrame) -> pd.Series:
    task_col = "task_identifier" if "task_identifier" in events else "task_id"
    stages = events["changed_value"].eq("Stage")
    standard = events["changed_value"].isin(STANDARD_STATUS_FIELDS)
    if not stages.any() or task_col not in events:
        return standard
    task_ids = events[task_col]
    finance = task_ids.astype("string").str.startswith(f"{FINANCE_PROJECT}-", na=False)
    finance_with_stage = task_ids[stages & finance]
    use_stage = task_ids.isin(finance_with_stage)
    return (use_stage & stages) | (~use_stage & standard)
