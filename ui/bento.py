"""ui/bento.py — дизайн-система Bento / Glassmorphism для Streamlit.

Модуль содержит:
* глобальные CSS-переменные и стили (тёмная и светлая палитры);
* компоненты ``render_hero``, ``render_section_header``, ``render_kpi_card``;
* шаблон Plotly с прозрачным фоном и палитрой Bento;
* helper ``render_plotly``, который отключает встроенную тему Streamlit.

Публичный API намеренно не зависит от внутренних деталей приложения: модуль
можно переиспользовать в других Streamlit-страницах.
"""
from __future__ import annotations

import html
import math
import uuid
from collections.abc import Iterable, Sequence
from typing import Any, Literal

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

ThemeMode = Literal["dark", "light"]

_FONT_STACK = (
    "'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont, "
    "'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
)

_ACCENT_GRADIENTS: dict[str, str] = {
    "emerald": "linear-gradient(135deg, #34d399 0%, #059669 100%)",
    "indigo": "linear-gradient(135deg, #818cf8 0%, #4f46e5 100%)",
    "violet": "linear-gradient(135deg, #c084fc 0%, #7c3aed 100%)",
    "cyan": "linear-gradient(135deg, #22d3ee 0%, #0891b2 100%)",
    "amber": "linear-gradient(135deg, #fbbf24 0%, #d97706 100%)",
}
_LIGHT_ACCENT_GRADIENTS: dict[str, str] = {
    "emerald": "linear-gradient(135deg, #10b981 0%, #047857 100%)",
    "indigo": "linear-gradient(135deg, #6366f1 0%, #4338ca 100%)",
    "violet": "linear-gradient(135deg, #a855f7 0%, #6d28d9 100%)",
    "cyan": "linear-gradient(135deg, #06b6d4 0%, #0e7490 100%)",
    "amber": "linear-gradient(135deg, #f59e0b 0%, #b45309 100%)",
}
THEME_SESSION_KEY = "bento_light_mode"
_ACCENT_NAMES = tuple(_ACCENT_GRADIENTS)

_ICON_PATHS: dict[str, str] = {
    "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "alert": (
        '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 '
        '1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/>'
        '<path d="M12 17h.01"/>'
    ),
    "bars": (
        '<path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/>'
    ),
    "check": (
        '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>'
        '<path d="m22 4-10 10.01-3-3"/>'
    ),
    "clock": (
        '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'
    ),
    "gauge": (
        '<path d="M3.34 19a10 10 0 1 1 17.32 0"/>'
        '<path d="m12 14 4-4"/><path d="M12 20h.01"/>'
    ),
    "layers": (
        '<path d="m12 2 9.5 5.5L12 13 2.5 7.5 12 2z"/>'
        '<path d="m2.5 12 9.5 5.5 9.5-5.5"/>'
        '<path d="m2.5 16.5 9.5 5.5 9.5-5.5"/>'
    ),
    "sparkles": (
        '<path d="m12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"/>'
        '<path d="M19 17v4"/><path d="M17 19h4"/>'
    ),
    "target": (
        '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/>'
        '<circle cx="12" cy="12" r="1"/>'
    ),
    "trending-down": (
        '<path d="m22 17-7.5-7.5-5 5L2 7"/><path d="M16 17h6v-6"/>'
    ),
    "trending-up": (
        '<path d="m22 7-7.5 7.5-5-5L2 17"/><path d="M16 7h6v6"/>'
    ),
    "users": (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
        '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
    ),
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
}


def _normalize_mode(mode: str | None) -> ThemeMode:
    return "light" if mode == "light" else "dark"


def active_theme_mode() -> ThemeMode:
    """Текущий режим оформления: состояние сессии или ``?theme=light|dark``."""
    try:
        value = st.session_state.get(THEME_SESSION_KEY)
        if value is None:
            query_value = st.query_params.get("theme")
            if query_value in ("light", "dark"):
                value = query_value == "light"
                st.session_state[THEME_SESSION_KEY] = value
        return "light" if value else "dark"
    except Exception:
        # Вне контекста Streamlit (тесты, импорт) безопасно считаем тему тёмной.
        return "dark"


def _resolve_mode(mode: str | None) -> ThemeMode:
    return _normalize_mode(mode) if mode is not None else active_theme_mode()


def bento_palette(mode: str | None = None) -> dict[str, Any]:
    """Вернуть согласованную палитру Bento для Plotly/CSS."""
    mode = _normalize_mode(mode)
    if mode == "light":
        return {
            "mode": mode,
            "text": "#0f172a",
            "muted": "#64748b",
            "slate": "#94a3b8",
            "grid": "rgba(15, 23, 42, 0.08)",
            "zero": "rgba(15, 23, 42, 0.16)",
            "line": "rgba(15, 23, 42, 0.12)",
            "hover_bg": "rgba(255, 255, 255, 0.97)",
            "hover_border": "rgba(15, 23, 42, 0.14)",
            "emerald": "#059669",
            "indigo": "#4f46e5",
            "violet": "#7c3aed",
            "cyan": "#0891b2",
            "amber": "#d97706",
            "rose": "#e11d48",
            "series": [
                "#059669",
                "#4f46e5",
                "#7c3aed",
                "#0891b2",
                "#d97706",
                "#e11d48",
                "#2563eb",
                "#db2777",
            ],
        }
    return {
        "mode": "dark",
        "text": "#e8edf7",
        "muted": "#94a3b8",
        "slate": "#64748b",
        "grid": "rgba(148, 163, 184, 0.14)",
        "zero": "rgba(148, 163, 184, 0.28)",
        "line": "rgba(148, 163, 184, 0.18)",
        "hover_bg": "rgba(10, 15, 28, 0.94)",
        "hover_border": "rgba(148, 163, 184, 0.35)",
        "emerald": "#34d399",
        "indigo": "#818cf8",
        "violet": "#c084fc",
        "cyan": "#22d3ee",
        "amber": "#fbbf24",
        "rose": "#fb7185",
        "series": [
            "#34d399",
            "#818cf8",
            "#c084fc",
            "#22d3ee",
            "#fbbf24",
            "#fb7185",
            "#60a5fa",
            "#f472b6",
        ],
    }


# Публичный алиас для страниц, которым нужны цвета без вызова функции.
BENTO_COLORS: dict[str, Any] = bento_palette("dark")


def _theme_vars(mode: ThemeMode) -> dict[str, str]:
    if mode == "light":
        return {
            "bg": "#f2f5fb",
            "color_scheme": "light",
            "text": "#0f172a",
            "muted": "rgba(15, 23, 42, 0.62)",
            "faint": "rgba(15, 23, 42, 0.42)",
            "surface": "rgba(255, 255, 255, 0.72)",
            "surface_soft": "rgba(255, 255, 255, 0.42)",
            "surface_strong": "rgba(255, 255, 255, 0.88)",
            "border": "rgba(15, 23, 42, 0.08)",
            "border_strong": "rgba(79, 70, 229, 0.28)",
            "shadow": "0 22px 55px rgba(15, 23, 42, 0.10)",
            "shadow_hover": "0 28px 70px rgba(15, 23, 42, 0.16)",
            "accent": "#059669",
            "accent_2": "#4f46e5",
            "accent_3": "#7c3aed",
            "good": "#059669",
            "good_bg": "rgba(5, 150, 105, 0.10)",
            "bad": "#e11d48",
            "bad_bg": "rgba(225, 29, 72, 0.10)",
            "neutral": "#64748b",
            "neutral_bg": "rgba(100, 116, 139, 0.10)",
            "input": "rgba(255, 255, 255, 0.78)",
            "input_hover": "rgba(255, 255, 255, 0.94)",
            "hover": "rgba(15, 23, 42, 0.05)",
            "popover": "rgba(255, 255, 255, 0.98)",
            "sidebar": "linear-gradient(180deg, rgba(255, 255, 255, 0.86), rgba(246, 249, 255, 0.94))",
            "value_gradient": "linear-gradient(180deg, #0f172a 0%, #334155 120%)",
            "heading_gradient": "linear-gradient(100deg, #0f172a 0%, #4338ca 52%, #047857 100%)",
            "mesh": (
                "radial-gradient(1100px 760px at 8% -10%, rgba(129, 140, 248, 0.26), transparent 62%), "
                "radial-gradient(900px 620px at 92% 4%, rgba(52, 211, 153, 0.18), transparent 58%), "
                "radial-gradient(860px 680px at 50% 108%, rgba(192, 132, 252, 0.20), transparent 60%), "
                "linear-gradient(180deg, #f5f7fc 0%, #eef1f8 55%, #e9edf6 100%)"
            ),
        }
    return {
        "bg": "#070b14",
        "color_scheme": "dark",
        "text": "#eef2ff",
        "muted": "rgba(226, 232, 240, 0.62)",
        "faint": "rgba(226, 232, 240, 0.40)",
        "surface": "rgba(255, 255, 255, 0.055)",
        "surface_soft": "rgba(255, 255, 255, 0.022)",
        "surface_strong": "rgba(255, 255, 255, 0.09)",
        "border": "rgba(255, 255, 255, 0.12)",
        "border_strong": "rgba(255, 255, 255, 0.24)",
        "shadow": "0 24px 60px rgba(0, 0, 0, 0.36)",
        "shadow_hover": "0 32px 78px rgba(0, 0, 0, 0.52)",
        "accent": "#34d399",
        "accent_2": "#818cf8",
        "accent_3": "#c084fc",
        "good": "#34d399",
        "good_bg": "rgba(52, 211, 153, 0.12)",
        "bad": "#fb7185",
        "bad_bg": "rgba(251, 113, 133, 0.12)",
        "neutral": "#94a3b8",
        "neutral_bg": "rgba(148, 163, 184, 0.12)",
        "input": "rgba(255, 255, 255, 0.055)",
        "input_hover": "rgba(255, 255, 255, 0.09)",
        "hover": "rgba(255, 255, 255, 0.07)",
        "popover": "rgba(10, 15, 28, 0.97)",
        "sidebar": "linear-gradient(180deg, rgba(11, 18, 32, 0.88), rgba(7, 11, 20, 0.97))",
        "value_gradient": "linear-gradient(180deg, #ffffff 0%, #c7d2fe 130%)",
        "heading_gradient": "linear-gradient(100deg, #ffffff 0%, #c7d2fe 48%, #6ee7b7 100%)",
        "mesh": (
            "radial-gradient(1100px 760px at 8% -10%, rgba(99, 102, 241, 0.32), transparent 62%), "
            "radial-gradient(900px 620px at 92% 4%, rgba(16, 185, 129, 0.20), transparent 58%), "
            "radial-gradient(860px 680px at 50% 108%, rgba(168, 85, 247, 0.22), transparent 60%), "
            "linear-gradient(180deg, #070b14 0%, #080d18 55%, #060911 100%)"
        ),
    }


_VARIABLES_TEMPLATE = """
:root {{
    color-scheme: {color_scheme};
    --bento-bg: {bg};
    --bento-text: {text};
    --bento-muted: {muted};
    --bento-faint: {faint};
    --bento-surface: {surface};
    --bento-surface-soft: {surface_soft};
    --bento-surface-strong: {surface_strong};
    --bento-border: {border};
    --bento-border-strong: {border_strong};
    --bento-shadow: {shadow};
    --bento-shadow-hover: {shadow_hover};
    --bento-accent: {accent};
    --bento-accent-2: {accent_2};
    --bento-accent-3: {accent_3};
    --bento-good: {good};
    --bento-good-bg: {good_bg};
    --bento-bad: {bad};
    --bento-bad-bg: {bad_bg};
    --bento-neutral: {neutral};
    --bento-neutral-bg: {neutral_bg};
    --bento-input: {input};
    --bento-input-hover: {input_hover};
    --bento-hover: {hover};
    --bento-popover: {popover};
    --bento-sidebar: {sidebar};
    --bento-value-gradient: {value_gradient};
    --bento-heading-gradient: {heading_gradient};
    --bento-mesh: {mesh};
}}
"""

_BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, .stApp,
.stApp *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded):not(.material-icons) {
    font-family: 'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont,
        'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
}

/* Не ломаем иконочный шрифт Streamlit. */
.stApp [data-testid="stIconMaterial"],
.stApp .material-symbols-rounded,
.stApp .material-icons {
    font-family: 'Material Symbols Rounded' !important;
    font-feature-settings: 'liga';
    -webkit-font-feature-settings: 'liga';
    letter-spacing: normal;
    text-transform: none;
}

/* ---------- Канва с mesh-градиентами ---------- */
.stApp,
[data-testid="stAppViewContainer"] {
    background-color: var(--bento-bg) !important;
    background-image: var(--bento-mesh) !important;
    background-attachment: fixed !important;
    color: var(--bento-text);
}

[data-testid="stAppViewContainer"] > .main,
[data-testid="stMain"] {
    background: transparent !important;
}

.block-container {
    max-width: 1580px;
    padding-top: 1.9rem;
    padding-bottom: 4rem;
    padding-left: 2rem;
    padding-right: 2rem;
}

[data-testid="stHeader"] {
    background: transparent !important;
}
[data-testid="stToolbar"] { background: transparent !important; }
#MainMenu, footer, [data-testid="stStatusWidget"], [data-testid="stDecoration"] {
    visibility: hidden;
    height: 0;
}
[data-testid="stDeployButton"], [data-testid="stToolbarActions"] {
    display: none !important;
}

/* ---------- Типографика ---------- */
.stApp h1 {
    color: var(--bento-text);
    font-size: clamp(1.9rem, 3.1vw, 2.75rem);
    line-height: 1.08;
    font-weight: 800;
    letter-spacing: -0.035em;
    margin-bottom: 0.35rem;
}
.stApp h2 {
    color: var(--bento-text);
    font-size: clamp(1.35rem, 2vw, 1.8rem);
    line-height: 1.2;
    font-weight: 700;
    letter-spacing: -0.025em;
}
.stApp h3, .stApp h4, .stApp h5, .stApp h6 {
    color: var(--bento-text);
    font-weight: 650;
    letter-spacing: -0.015em;
}
.stApp p, .stApp li, .stApp label, .stApp span {
    color: inherit;
}
.stApp a { color: var(--bento-accent-2); }
[data-testid="stCaptionContainer"], .stCaption {
    color: var(--bento-muted) !important;
}
hr {
    border: none;
    border-top: 1px solid var(--bento-border);
    margin: 1.15rem 0;
}

/* ---------- Сайдбар ---------- */
[data-testid="stSidebar"] {
    background: var(--bento-sidebar) !important;
    border-right: 1px solid var(--bento-border);
    box-shadow: 24px 0 70px rgba(0, 0, 0, 0.14);
    backdrop-filter: blur(22px) saturate(140%);
    -webkit-backdrop-filter: blur(22px) saturate(140%);
}
[data-testid="stSidebar"] > div { background: transparent !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: var(--bento-text); }
[data-testid="stSidebar"] [data-testid="stMetric"] {
    padding: 0.7rem 0.8rem;
    border-radius: 0.9rem;
}

/* ---------- Карточки и панели ---------- */
.glass-card,
.bento-panel {
    position: relative;
    background: linear-gradient(150deg, var(--bento-surface), var(--bento-surface-soft));
    border: 1px solid var(--bento-border);
    border-radius: 1.25rem;
    box-shadow: var(--bento-shadow), inset 0 1px 0 rgba(255, 255, 255, 0.07);
    backdrop-filter: blur(16px) saturate(140%);
    -webkit-backdrop-filter: blur(16px) saturate(140%);
    transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
}
.glass-card:hover,
.bento-panel:hover {
    transform: translateY(-4px);
    border-color: var(--bento-border-strong);
    box-shadow: var(--bento-shadow-hover), inset 0 1px 0 rgba(255, 255, 255, 0.10);
}

[data-testid="stVerticalBlock"]:has(
    > :is([data-testid="element-container"], [data-testid="stElementContainer"]) .bento-panel-marker
) {
    background: linear-gradient(150deg, var(--bento-surface), var(--bento-surface-soft)) !important;
    border: 1px solid var(--bento-border) !important;
    border-radius: 1.25rem !important;
    padding: 1rem 1.1rem !important;
    box-shadow: var(--bento-shadow), inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
    backdrop-filter: blur(16px) saturate(140%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(140%) !important;
}
[data-testid="stVerticalBlock"]:has(
    > :is([data-testid="element-container"], [data-testid="stElementContainer"]) .bento-panel-marker
)
    > :is([data-testid="element-container"], [data-testid="stElementContainer"]):has(.bento-panel-marker) {
    display: none !important;
}
[data-testid="stVerticalBlock"]:has(
    > :is([data-testid="element-container"], [data-testid="stElementContainer"]) .bento-panel-marker
)
    :is(.stPlotlyChart, [data-testid="stPlotlyChart"]) {
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
    padding: 0 !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
}
[data-testid="stVerticalBlock"]:has(
    > :is([data-testid="element-container"], [data-testid="stElementContainer"]) .bento-panel-marker
)
    [data-testid="stDataFrame"] {
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
}

/* ---------- KPI-карточки ---------- */
.bento-kpi {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
    min-height: 184px;
    height: 100%;
    padding: 1.15rem 1.2rem 0.95rem;
    overflow: hidden;
    background: linear-gradient(150deg, var(--bento-surface), var(--bento-surface-soft));
    border: 1px solid var(--bento-border);
    border-radius: 1.25rem;
    box-shadow: var(--bento-shadow), inset 0 1px 0 rgba(255, 255, 255, 0.07);
    backdrop-filter: blur(16px) saturate(140%);
    -webkit-backdrop-filter: blur(16px) saturate(140%);
    transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
    animation: bento-rise 0.45s ease both;
}
.bento-kpi::after {
    content: "";
    position: absolute;
    top: -95px;
    right: -75px;
    width: 190px;
    height: 190px;
    border-radius: 999px;
    background: var(--kpi-accent);
    filter: blur(48px);
    opacity: 0.20;
    pointer-events: none;
}
.bento-kpi:hover {
    transform: translateY(-4px);
    border-color: var(--bento-border-strong);
    box-shadow: var(--bento-shadow-hover), inset 0 1px 0 rgba(255, 255, 255, 0.11);
}
.bento-kpi__head {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.7rem;
}
.bento-kpi__icon {
    display: inline-grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border-radius: 0.85rem;
    color: #fff;
    background: var(--kpi-accent);
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
}
.bento-kpi__icon svg { width: 20px; height: 20px; }
.bento-kpi__badge {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.22rem 0.5rem;
    border: 1px solid transparent;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    white-space: nowrap;
}
.bento-kpi__badge svg { width: 12px; height: 12px; }
.bento-kpi__badge--good {
    color: var(--bento-good);
    background: var(--bento-good-bg);
    border-color: rgba(52, 211, 153, 0.22);
}
.bento-kpi__badge--bad {
    color: var(--bento-bad);
    background: var(--bento-bad-bg);
    border-color: rgba(251, 113, 133, 0.22);
}
.bento-kpi__badge--neutral {
    color: var(--bento-neutral);
    background: var(--bento-neutral-bg);
    border-color: var(--bento-border);
}
.bento-kpi__body {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    margin-top: 0.25rem;
}
.bento-kpi__label {
    color: var(--bento-muted);
    font-size: 0.76rem;
    font-weight: 550;
    letter-spacing: 0.015em;
}
.bento-kpi__value {
    font-size: clamp(1.7rem, 2.35vw, 2.35rem);
    line-height: 1.08;
    font-weight: 750;
    letter-spacing: -0.045em;
    background: var(--bento-value-gradient);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}
.bento-kpi__foot {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 0.6rem;
    margin-top: auto;
    color: var(--bento-faint);
    font-size: 0.68rem;
    line-height: 1.35;
}
.bento-kpi__spark {
    flex: 0 0 98px;
    width: 98px;
    height: 30px;
    opacity: 0.9;
}
.bento-kpi__spark svg { width: 100%; height: 100%; overflow: visible; }

/* ---------- Hero и section headers ---------- */
.bento-hero {
    position: relative;
    overflow: hidden;
    padding: 1.55rem 1.7rem;
    margin: 0.15rem 0 1.15rem;
    background: linear-gradient(145deg, var(--bento-surface), var(--bento-surface-soft));
    border: 1px solid var(--bento-border);
    border-radius: 1.5rem;
    box-shadow: var(--bento-shadow), inset 0 1px 0 rgba(255, 255, 255, 0.07);
    backdrop-filter: blur(18px) saturate(140%);
    -webkit-backdrop-filter: blur(18px) saturate(140%);
    animation: bento-rise 0.5s ease both;
}
.bento-hero::before {
    content: "";
    position: absolute;
    top: -130px;
    right: -80px;
    width: 360px;
    height: 360px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(129, 140, 248, 0.32), transparent 66%);
    filter: blur(12px);
    pointer-events: none;
}
.bento-hero::after {
    content: "";
    position: absolute;
    bottom: -170px;
    left: 28%;
    width: 420px;
    height: 300px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(52, 211, 153, 0.18), transparent 68%);
    filter: blur(16px);
    pointer-events: none;
}
.bento-hero__copy { position: relative; z-index: 1; max-width: 920px; }
.bento-hero__title {
    margin: 0.2rem 0 0.35rem;
    font-size: clamp(1.65rem, 2.7vw, 2.35rem);
    line-height: 1.08;
    font-weight: 800;
    letter-spacing: -0.045em;
    background: var(--bento-heading-gradient);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}
.bento-hero__subtitle {
    max-width: 76ch;
    margin: 0;
    color: var(--bento-muted);
    font-size: 0.9rem;
    line-height: 1.6;
}
.bento-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-top: 0.95rem;
}
.bento-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.65rem;
    border: 1px solid var(--bento-border);
    border-radius: 999px;
    background: var(--bento-surface-strong);
    color: var(--bento-muted);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.01em;
}
.bento-eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    color: var(--bento-accent);
    font-size: 0.66rem;
    font-weight: 800;
    letter-spacing: 0.16em;
    text-transform: uppercase;
}
.bento-eyebrow::before {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 999px;
    background: currentColor;
    box-shadow: 0 0 14px currentColor;
}
.bento-section { margin: 0.15rem 0 0.9rem; }
.bento-section__title {
    margin: 0.18rem 0 0;
    color: var(--bento-text);
    font-size: 1.08rem;
    line-height: 1.3;
    font-weight: 700;
    letter-spacing: -0.02em;
}
.bento-section__subtitle {
    margin: 0.2rem 0 0;
    color: var(--bento-muted);
    font-size: 0.8rem;
    line-height: 1.5;
}

/* ---------- Signal / info panel ---------- */
.bento-panel {
    padding: 1.15rem 1.2rem;
    height: 100%;
}
.bento-panel__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.8rem;
}
.bento-panel__title {
    margin: 0.15rem 0 0;
    color: var(--bento-text);
    font-size: 1rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}
.bento-status {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.55rem;
    border: 1px solid transparent;
    border-radius: 999px;
    font-size: 0.67rem;
    font-weight: 700;
    white-space: nowrap;
}
.bento-status--good {
    color: var(--bento-good);
    background: var(--bento-good-bg);
    border-color: rgba(52, 211, 153, 0.22);
}
.bento-status--bad {
    color: var(--bento-bad);
    background: var(--bento-bad-bg);
    border-color: rgba(251, 113, 133, 0.22);
}
.bento-status--neutral {
    color: var(--bento-neutral);
    background: var(--bento-neutral-bg);
    border-color: var(--bento-border);
}
.bento-dot {
    width: 6px;
    height: 6px;
    border-radius: 999px;
    background: currentColor;
    box-shadow: 0 0 12px currentColor;
}
.bento-signal__value {
    margin-top: 1.05rem;
    color: var(--bento-text);
    font-size: 2rem;
    line-height: 1.1;
    font-weight: 750;
    letter-spacing: -0.045em;
}
.bento-signal__label {
    margin: 0.15rem 0 0.85rem;
    color: var(--bento-muted);
    font-size: 0.74rem;
}
.bento-panel__rows { display: flex; flex-direction: column; }
.bento-panel__row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.9rem;
    padding: 0.55rem 0;
    border-top: 1px solid var(--bento-border);
    font-size: 0.78rem;
}
.bento-panel__key { color: var(--bento-muted); }
.bento-panel__val { color: var(--bento-text); font-weight: 650; text-align: right; }
.bento-panel__val--warn { color: var(--bento-bad); }
.bento-panel__foot {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--bento-border);
    color: var(--bento-faint);
    font-size: 0.71rem;
    line-height: 1.55;
}

/* ---------- Нативные метрики Streamlit ---------- */
[data-testid="stMetric"] {
    background: linear-gradient(150deg, var(--bento-surface), var(--bento-surface-soft)) !important;
    border: 1px solid var(--bento-border) !important;
    border-radius: 1rem !important;
    padding: 0.95rem 1.05rem !important;
    box-shadow: var(--bento-shadow) !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
}
[data-testid="stMetricLabel"] p {
    color: var(--bento-muted) !important;
    font-size: 0.76rem !important;
    font-weight: 550 !important;
}
[data-testid="stMetricValue"] {
    color: var(--bento-text) !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em;
}
[data-testid="stMetricDelta"] { font-weight: 600; }

/* ---------- Графики и таблицы ---------- */
:is(.stPlotlyChart, [data-testid="stPlotlyChart"]) {
    background: linear-gradient(150deg, var(--bento-surface), var(--bento-surface-soft)) !important;
    border: 1px solid var(--bento-border) !important;
    border-radius: 1.25rem !important;
    padding: 0.35rem 0.4rem 0 !important;
    box-shadow: var(--bento-shadow) !important;
    backdrop-filter: blur(16px) saturate(140%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(140%) !important;
    transition: border-color 0.25s ease, box-shadow 0.25s ease;
}
:is(.stPlotlyChart, [data-testid="stPlotlyChart"]):hover {
    border-color: var(--bento-border-strong) !important;
    box-shadow: var(--bento-shadow-hover) !important;
}
:is(.stPlotlyChart, [data-testid="stPlotlyChart"]) .modebar { opacity: 0.55; }

[data-testid="stDataFrame"], [data-testid="stTable"] {
    overflow: hidden;
    border: 1px solid var(--bento-border) !important;
    border-radius: 1rem !important;
    background: var(--bento-surface) !important;
    box-shadow: var(--bento-shadow) !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
}
[data-testid="stDataFrame"] > div,
[data-testid="stTable"] > div {
    background: transparent !important;
}

/* ---------- Кнопки ---------- */
.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button {
    border-radius: 0.85rem !important;
    border: 1px solid var(--bento-border) !important;
    background: var(--bento-surface-strong) !important;
    color: var(--bento-text) !important;
    font-weight: 600 !important;
    padding: 0.5rem 1.05rem !important;
    box-shadow: none !important;
    transition: transform 0.18s ease, background 0.18s ease,
        border-color 0.18s ease, box-shadow 0.18s ease !important;
}
.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {
    transform: translateY(-1px);
    background: var(--bento-input-hover) !important;
    border-color: var(--bento-border-strong) !important;
}
.stButton > button:active,
.stDownloadButton > button:active,
.stFormSubmitButton > button:active { transform: translateY(0); }
[data-testid="baseButton-primary"],
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
    border-color: transparent !important;
    color: #ffffff !important;
    box-shadow: 0 12px 30px rgba(99, 102, 241, 0.28) !important;
}
[data-testid="baseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    box-shadow: 0 16px 38px rgba(99, 102, 241, 0.38) !important;
}

/* ---------- Поля ввода и выпадающие списки ---------- */
.stTextInput input,
.stNumberInput input,
.stDateInput input,
[data-baseweb="input"],
[data-baseweb="textarea"],
[data-baseweb="select"] > div {
    border-radius: 0.85rem !important;
    border: 1px solid var(--bento-border) !important;
    background: var(--bento-input) !important;
    color: var(--bento-text) !important;
    box-shadow: none !important;
}
[data-baseweb="input"]:focus-within,
[data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within,
.stTextInput input:focus {
    border-color: var(--bento-accent-2) !important;
    box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.18) !important;
}
[data-baseweb="select"] svg { fill: var(--bento-muted); }
[data-testid="stWidgetLabel"] p {
    color: var(--bento-muted) !important;
    font-size: 0.76rem !important;
    font-weight: 550 !important;
}
[data-baseweb="popover"] { color: var(--bento-text) !important; }
[data-baseweb="popover"] ul,
[data-baseweb="popover"] [role="listbox"] {
    background: var(--bento-popover) !important;
    border: 1px solid var(--bento-border) !important;
    border-radius: 0.9rem !important;
    box-shadow: var(--bento-shadow) !important;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
}
[data-baseweb="popover"] li {
    background: transparent !important;
    color: var(--bento-text) !important;
}
[data-baseweb="popover"] li:hover {
    background: var(--bento-hover) !important;
}

/* ---------- Табы, радио, экспандеры ---------- */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.3rem;
    padding: 0.3rem;
    border: 1px solid var(--bento-border);
    border-radius: 1rem;
    background: var(--bento-surface);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 0.7rem;
    color: var(--bento-muted);
    font-weight: 600;
    padding: 0.4rem 0.85rem;
}
.stTabs [aria-selected="true"] {
    background: var(--bento-surface-strong) !important;
    color: var(--bento-text) !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none; }

div[role="radiogroup"] { gap: 0.3rem; }
div[role="radiogroup"] label {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    width: 100%;
    padding: 0.55rem 0.7rem;
    border: 1px solid transparent;
    border-radius: 0.8rem;
    transition: background 0.18s ease, border-color 0.18s ease;
}
div[role="radiogroup"] label:hover { background: var(--bento-hover); }
div[role="radiogroup"] label p { color: var(--bento-muted); }
div[role="radiogroup"] label:has(input:checked) {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.20), rgba(16, 185, 129, 0.10));
    border-color: rgba(129, 140, 248, 0.32);
}
div[role="radiogroup"] label:has(input:checked) p {
    color: var(--bento-text) !important;
    font-weight: 600;
}

[data-testid="stExpander"] {
    overflow: hidden;
    border: 1px solid var(--bento-border) !important;
    border-radius: 1rem !important;
    background: var(--bento-surface) !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
}
[data-testid="stExpander"] summary { color: var(--bento-text); }
[data-testid="stForm"] {
    padding: 1.2rem !important;
    border: 1px solid var(--bento-border) !important;
    border-radius: 1.25rem !important;
    background: linear-gradient(150deg, var(--bento-surface), var(--bento-surface-soft)) !important;
    box-shadow: var(--bento-shadow) !important;
    backdrop-filter: blur(18px) !important;
    -webkit-backdrop-filter: blur(18px) !important;
}
[data-testid="stAlert"] {
    border: 1px solid var(--bento-border) !important;
    border-radius: 1rem !important;
    background: var(--bento-surface) !important;
    backdrop-filter: blur(14px) !important;
    -webkit-backdrop-filter: blur(14px) !important;
}
[data-testid="stFileUploaderDropzone"] {
    border: 1px dashed var(--bento-border-strong);
    border-radius: 1rem;
    background: var(--bento-surface);
}
[data-testid="stFileUploaderDropzone"]:hover { background: var(--bento-hover); }

/* ---------- Скроллбар и анимации ---------- */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    border: 2px solid transparent;
    border-radius: 999px;
    background: var(--bento-border-strong);
    background-clip: padding-box;
}
::-webkit-scrollbar-thumb:hover { background: var(--bento-accent-2); background-clip: padding-box; }

@keyframes bento-rise {
    from { opacity: 0; transform: translateY(9px); }
    to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 900px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
        padding-top: 1.2rem;
    }
    .bento-hero { padding: 1.2rem 1.15rem; }
    .bento-kpi { min-height: 164px; }
}

@media (prefers-reduced-motion: reduce) {
    .bento-kpi, .bento-hero, .glass-card, .bento-panel {
        animation: none !important;
        transition: none !important;
    }
    .bento-kpi:hover, .glass-card:hover, .bento-panel:hover { transform: none; }
}
"""


_LIGHT_CSS = """
/* ---------- Светлая тема: точечные исправления ---------- */
.stApp { color-scheme: light; }

/* BaseWeb-поля: внутренний контейнер в тёмной теме остаётся тёмным. */
[data-baseweb="base-input"],
[data-baseweb="input"],
[data-baseweb="textarea"],
[data-baseweb="select"] > div {
    background-color: var(--bento-input) !important;
    color: var(--bento-text) !important;
}
[data-baseweb="base-input"] input,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea {
    background-color: transparent !important;
    color: var(--bento-text) !important;
    caret-color: var(--bento-accent-2);
}
[data-baseweb="base-input"] input::placeholder,
[data-baseweb="textarea"] textarea::placeholder {
    color: var(--bento-faint) !important;
}
[data-baseweb="base-input"] button svg,
[data-baseweb="input"] button svg,
[data-testid="stTextInput"] button svg {
    fill: var(--bento-muted) !important;
    color: var(--bento-muted) !important;
}
[data-baseweb="base-input"] button:hover,
[data-baseweb="input"] button:hover {
    background: var(--bento-hover) !important;
}

/* Уведомления: тон текста наследуется от тёмной темы Streamlit. */
[data-testid="stNotification"] { color: var(--bento-text) !important; }
[data-testid="stNotification"] p,
[data-testid="stNotification"] [data-testid="stMarkdownContainer"],
[data-testid="stNotification"] [data-testid^="stNotificationContent"] {
    color: var(--bento-text) !important;
}

/* Dataframe рисуется на canvas цветами тёмной темы — инвертируем канвас. */
[data-testid="stDataFrame"] { background: var(--bento-surface-strong) !important; }
[data-testid="stDataFrame"] canvas { filter: invert(1) hue-rotate(180deg); }
[data-testid="stDataFrame"] > div { background: transparent !important; }
[data-testid="stElementToolbar"] > div {
    background: var(--bento-surface-strong) !important;
    color: var(--bento-text) !important;
    border: 1px solid var(--bento-border);
    border-radius: 0.7rem;
}
[data-testid="stElementToolbar"] button,
[data-testid="stElementToolbarButtonIcon"] { color: var(--bento-text) !important; }

[data-testid="stToast"],
[data-baseweb="tooltip"],
[data-baseweb="calendar"] {
    background: var(--bento-popover) !important;
    color: var(--bento-text) !important;
    border: 1px solid var(--bento-border) !important;
    box-shadow: var(--bento-shadow) !important;
}
[data-baseweb="calendar"] * { color: var(--bento-text) !important; }
[data-testid="stExpander"] summary:hover { background: var(--bento-hover) !important; }
[data-testid="stFileUploaderDropzone"] { background: var(--bento-input) !important; }
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzone"] small {
    color: var(--bento-muted) !important;
}
[data-testid="stFileUploaderDropzone"] svg {
    fill: var(--bento-muted) !important;
    color: var(--bento-muted) !important;
}
[data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploaderDropzone"] button * { color: #ffffff !important; }
[data-testid="stSidebar"] { box-shadow: 24px 0 60px rgba(15, 23, 42, 0.10); }
"""


def _accent_css(mode: ThemeMode) -> str:
    gradients = _LIGHT_ACCENT_GRADIENTS if mode == "light" else _ACCENT_GRADIENTS
    rules = "\n".join(
        f".bento-kpi--{name} {{ --kpi-accent: {gradient}; }}"
        for name, gradient in gradients.items()
    )
    return f"\n/* ---------- KPI accents ---------- */\n{rules}\n"


def _build_css(mode: ThemeMode) -> str:
    variables = _VARIABLES_TEMPLATE.format(**_theme_vars(mode))
    light_css = _LIGHT_CSS if mode == "light" else ""
    return f"<style>{variables}{_accent_css(mode)}{_BASE_CSS}{light_css}</style>"


def activate_plotly_theme(mode: str | None = None) -> None:
    """Сделать шаблон Bento глобальным шаблоном Plotly."""
    pio.templates.default = f"bento_{_resolve_mode(mode)}"


def inject_theme(mode: str | None = None) -> None:
    """Подключить глобальную Bento/Glass-тему и Plotly-шаблон.

    ``mode=None`` берёт текущий режим из сессии/URL (по умолчанию ``dark``).
    """
    mode = _resolve_mode(mode)
    st.markdown(_build_css(mode), unsafe_allow_html=True)
    activate_plotly_theme(mode)


def _persist_theme_to_query() -> None:
    try:
        st.query_params["theme"] = (
            "light" if st.session_state.get(THEME_SESSION_KEY) else "dark"
        )
    except Exception:
        pass


def render_theme_toggle(*, key: str = THEME_SESSION_KEY) -> ThemeMode:
    """Переключатель тёмной/светлой темы для сайдбара или страницы входа."""
    st.toggle(
        "Светлая тема",
        key=key,
        help="Переключить светлое и тёмное оформление.",
        on_change=_persist_theme_to_query,
    )
    return active_theme_mode()


def glass_panel_marker() -> None:
    """Невидимый маркер: превращает текущий ``st.container()`` в glass-панель."""
    st.markdown(
        '<span class="bento-panel-marker" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )


def _icon_svg(name: str, size: int = 20) -> str:
    key = (name or "").strip().lower().replace("_", "-")
    path = _ICON_PATHS.get(key, _ICON_PATHS["sparkles"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{path}</svg>'
    )


def _arrow_svg(direction: str) -> str:
    if direction == "up":
        path = '<path d="M7 17 17 7"/><path d="M9 7h8v8"/>'
    elif direction == "down":
        path = '<path d="M7 7l10 10"/><path d="M17 9v8H9"/>'
    else:
        path = '<path d="M5 12h14"/>'
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{path}</svg>'
    )


def _sparkline_svg(
    values: Sequence[float] | Iterable[float],
    color: str,
    width: int = 98,
    height: int = 30,
) -> str:
    points: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            points.append(number)
    if len(points) < 2:
        return ""

    low, high = min(points), max(points)
    span = high - low or 1.0
    pad = 2.0
    usable_w = width - pad * 2
    usable_h = height - pad * 2
    step = usable_w / (len(points) - 1)
    coords = [
        (pad + index * step, pad + usable_h - ((value - low) / span) * usable_h)
        for index, value in enumerate(points)
    ]
    line = " ".join(
        f"{'M' if index == 0 else 'L'}{x:.1f},{y:.1f}"
        for index, (x, y) in enumerate(coords)
    )
    area = (
        f"{line} L{coords[-1][0]:.1f},{height - pad:.1f} "
        f"L{coords[0][0]:.1f},{height - pad:.1f} Z"
    )
    gradient_id = f"bento-spark-{uuid.uuid4().hex[:8]}"
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        'role="img" aria-hidden="true">'
        f'<defs><linearGradient id="{gradient_id}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.28"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        "</linearGradient></defs>"
        f'<path d="{area}" fill="url(#{gradient_id})"/>'
        f'<path d="{line}" fill="none" stroke="{color}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
        "</svg>"
    )


def kpi_card_html(
    title: str,
    value: str,
    change_pct: float | None,
    trend_direction: str,
    icon_name: str,
    *,
    positive_is_good: bool = True,
    caption: str | None = None,
    accent: str = "indigo",
    sparkline_values: Sequence[float] | Iterable[float] | None = None,
    mode: str | None = None,
) -> str:
    """Собрать HTML KPI-карточки (удобно тестировать без Streamlit)."""
    title_safe = html.escape(str(title))
    value_safe = html.escape(str(value))
    caption_safe = html.escape(str(caption)) if caption else ""
    direction = trend_direction if trend_direction in {"up", "down", "flat"} else "flat"

    tone = "neutral"
    if change_pct is not None and math.isfinite(float(change_pct)) and abs(float(change_pct)) >= 0.05:
        improving = (float(change_pct) > 0) == bool(positive_is_good)
        tone = "good" if improving else "bad"

    if change_pct is None or not math.isfinite(float(change_pct)):
        delta_label = "—"
    else:
        delta_label = f"{float(change_pct):+.1f}%"

    accent_key = accent if accent in _ACCENT_NAMES else "indigo"
    spark_color = bento_palette(_normalize_mode(mode))[accent_key]
    spark = (
        _sparkline_svg(sparkline_values, spark_color)
        if sparkline_values is not None
        else ""
    )
    foot = (
        f'<span class="bento-kpi__foot-text">{caption_safe}</span>'
        if caption_safe
        else '<span class="bento-kpi__foot-text"></span>'
    )
    spark_html = f'<span class="bento-kpi__spark">{spark}</span>' if spark else ""

    return (
        f'<div class="bento-kpi bento-kpi--{accent_key}">'
        '<div class="bento-kpi__head">'
        f'<span class="bento-kpi__icon">{_icon_svg(icon_name)}</span>'
        f'<span class="bento-kpi__badge bento-kpi__badge--{tone}">'
        f"{_arrow_svg(direction)}<span>{delta_label}</span></span>"
        "</div>"
        '<div class="bento-kpi__body">'
        f'<span class="bento-kpi__label">{title_safe}</span>'
        f'<span class="bento-kpi__value">{value_safe}</span>'
        "</div>"
        f'<div class="bento-kpi__foot">{foot}{spark_html}</div>'
        "</div>"
    )


def render_kpi_card(
    title: str,
    value: str,
    change_pct: float | None,
    trend_direction: str,
    icon_name: str,
    *,
    positive_is_good: bool = True,
    caption: str | None = None,
    accent: str = "indigo",
    sparkline_values: Sequence[float] | Iterable[float] | None = None,
    mode: str | None = None,
) -> None:
    """Отрисовать KPI-карточку в стиле Bento.

    Параметры
    ---------
    title:
        Подпись метрики.
    value:
        Крупное форматированное значение.
    change_pct:
        Изменение в процентах (``+4.2`` / ``-1.1``) или ``None``.
    trend_direction:
        ``"up"``, ``"down"`` или ``"flat"`` — направление стрелки.
    icon_name:
        Имя иконки из встроенного набора (``clock``, ``gauge``, ``layers`` ...).
    positive_is_good:
        Для метрик вида «чем меньше, тем лучше» передайте ``False``.
    caption:
        Подпись под значением, например «к прошлому месяцу».
    accent:
        ``emerald`` / ``indigo`` / ``violet`` / ``cyan`` / ``amber``.
    sparkline_values:
        Набор чисел для мини-графика в правом нижнем углу.
    mode:
        ``dark`` / ``light``; по умолчанию — активная тема сессии.
    """
    st.markdown(
        kpi_card_html(
            title,
            value,
            change_pct,
            trend_direction,
            icon_name,
            positive_is_good=positive_is_good,
            caption=caption,
            accent=accent,
            sparkline_values=sparkline_values,
            mode=mode if mode is not None else active_theme_mode(),
        ),
        unsafe_allow_html=True,
    )


def render_hero(
    title: str,
    subtitle: str | None = None,
    *,
    eyebrow: str | None = None,
    chips: Sequence[str] | None = None,
) -> None:
    """Отрисовать hero-блок страницы."""
    chip_html = "".join(
        f'<span class="bento-chip">{html.escape(str(chip))}</span>'
        for chip in (chips or ())
    )
    eyebrow_html = (
        f'<span class="bento-eyebrow">{html.escape(str(eyebrow))}</span>'
        if eyebrow
        else ""
    )
    subtitle_html = (
        f'<p class="bento-hero__subtitle">{html.escape(str(subtitle))}</p>'
        if subtitle
        else ""
    )
    st.markdown(
        '<div class="bento-hero"><div class="bento-hero__copy">'
        f"{eyebrow_html}"
        f'<div class="bento-hero__title">{html.escape(str(title))}</div>'
        f"{subtitle_html}"
        f'<div class="bento-chips">{chip_html}</div>'
        "</div></div>",
        unsafe_allow_html=True,
    )


def render_section_header(
    title: str,
    subtitle: str | None = None,
    *,
    eyebrow: str | None = None,
) -> None:
    """Отрисовать заголовок секции в стиле Bento."""
    eyebrow_html = (
        f'<span class="bento-eyebrow">{html.escape(str(eyebrow))}</span>'
        if eyebrow
        else ""
    )
    subtitle_html = (
        f'<p class="bento-section__subtitle">{html.escape(str(subtitle))}</p>'
        if subtitle
        else ""
    )
    st.markdown(
        '<div class="bento-section">'
        f"{eyebrow_html}"
        f'<div class="bento-section__title">{html.escape(str(title))}</div>'
        f"{subtitle_html}</div>",
        unsafe_allow_html=True,
    )


def plotly_template(mode: str | None = None) -> go.layout.Template:
    """Шаблон Plotly: прозрачный фон, Inter/SF Pro, палитра Bento."""
    mode = _resolve_mode(mode)
    palette = bento_palette(mode)
    axis_common = dict(
        showgrid=False,
        zeroline=False,
        linecolor=palette["line"],
        ticks="outside",
        ticklen=4,
        tickcolor="rgba(0,0,0,0)",
        tickfont=dict(family=_FONT_STACK, color=palette["muted"], size=11),
        title=dict(font=dict(family=_FONT_STACK, color=palette["muted"], size=12)),
        automargin=True,
    )
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family=_FONT_STACK, color=palette["text"], size=13),
            title=dict(
                x=0,
                xanchor="left",
                y=0.98,
                yanchor="top",
                font=dict(family=_FONT_STACK, color=palette["text"], size=16),
            ),
            colorway=palette["series"],
            hovermode="closest",
            hoverlabel=dict(
                bgcolor=palette["hover_bg"],
                bordercolor=palette["hover_border"],
                font=dict(family=_FONT_STACK, color=palette["text"], size=12),
                align="left",
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                x=0,
                xanchor="left",
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
                font=dict(family=_FONT_STACK, color=palette["muted"], size=11),
            ),
            margin=dict(l=10, r=14, t=54, b=12),
            bargap=0.34,
            bargroupgap=0.08,
            barcornerradius=6,
            modebar=dict(
                bgcolor="rgba(0,0,0,0)",
                color=palette["muted"],
                activecolor=palette["accent"] if "accent" in palette else palette["emerald"],
                orientation="h",
            ),
            xaxis={**axis_common, "showgrid": False, "zeroline": False},
            yaxis={
                **axis_common,
                "showgrid": True,
                "gridcolor": palette["grid"],
                "gridwidth": 1,
                "zeroline": False,
            },
            polar=dict(
                bgcolor="rgba(0,0,0,0)",
                radialaxis=dict(gridcolor=palette["grid"], linecolor=palette["line"]),
                angularaxis=dict(gridcolor=palette["grid"], linecolor=palette["line"]),
            ),
        )
    )


def apply_plotly_theme(fig: go.Figure, mode: str | None = None) -> go.Figure:
    """Применить Bento-шаблон к готовой фигуре, сохраняя её данные."""
    mode = _resolve_mode(mode)
    palette = bento_palette(mode)
    fig.update_layout(
        template=plotly_template(mode),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=_FONT_STACK, color=palette["text"], size=13),
        hoverlabel=dict(
            bgcolor=palette["hover_bg"],
            bordercolor=palette["hover_border"],
            font=dict(family=_FONT_STACK, color=palette["text"], size=12),
        ),
        legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0),
    )
    return fig


def render_plotly(
    fig: go.Figure,
    *,
    key: str | None = None,
    mode: str | None = None,
    height: int | None = None,
) -> None:
    """Отрисовать Plotly-график с прозрачным фоном и темой Bento."""
    apply_plotly_theme(fig, mode)
    if height is not None:
        fig.update_layout(height=height)
    st.plotly_chart(
        fig,
        use_container_width=True,
        theme=None,
        key=key,
        config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
    )


# Регистрируем шаблоны один раз при импорте. Значение по умолчанию выставляет
# inject_theme(), чтобы не влиять на другие Plotly-приложения в процессе.
for _mode in ("dark", "light"):
    pio.templates[f"bento_{_mode}"] = plotly_template(_mode)
del _mode
