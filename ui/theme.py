"""ui/theme.py — Фирменный стиль Контура для Streamlit.

Палитра и типографика взяты из брендбука https://in.kontur.ru/brandbook:
шрифт Lab Grotesque K, серый фон поверхностей #F6F6F6, текст #222222,
акцент — голубой продукта #2291FF.
"""
import streamlit as st

_FONT_URL = "https://s.kontur.ru/common-v2/fonts/LabGrotesque/LabGrotesque.css"

_THEME_CSS = """
<style>
@import url('https://s.kontur.ru/common-v2/fonts/LabGrotesque/LabGrotesque.css');

:root {
    --kontur-black: #222222;
    --kontur-gray: #F6F6F6;
    --kontur-blue: #2291FF;
    --kontur-blue-dark: #153177;
    --kontur-blue-press: #0B6BD0;
    --kontur-border: rgba(34, 34, 34, 0.10);
    --kontur-muted: rgba(34, 34, 34, 0.55);
}

html, body, .stApp,
.stApp *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded):not(.material-icons) {
    font-family: 'Lab Grotesque', 'Inter', -apple-system, BlinkMacSystemFont,
        'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
}

/* Не трогаем иконочный шрифт — иначе иконки превращаются в текст
   (например, keyboard_double_arrow_left или upload). */
.stApp [data-testid="stIconMaterial"],
.stApp .material-symbols-rounded,
.stApp .material-icons {
    font-family: 'Material Symbols Rounded' !important;
    font-feature-settings: 'liga';
    -webkit-font-feature-settings: 'liga';
    letter-spacing: normal;
    text-transform: none;
}

/* --- Канва и хром --- */
.stApp, [data-testid="stAppViewContainer"] {
    background: var(--kontur-gray);
    color: var(--kontur-black);
}
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer, [data-testid="stStatusWidget"] { visibility: hidden; height: 0; }
[data-testid="stDecoration"] { display: none; }

/* --- Типографика --- */
.stApp h1 {
    font-size: 40px; line-height: 46px; font-weight: 700;
    letter-spacing: -0.02em; color: var(--kontur-black);
}
.stApp h2 { font-size: 28px; line-height: 34px; font-weight: 600; color: var(--kontur-black); }
.stApp h3 { font-size: 22px; line-height: 28px; font-weight: 600; color: var(--kontur-black); }
.stApp h4 { font-size: 18px; line-height: 24px; font-weight: 600; }
.stApp h5, .stApp h6 { font-weight: 600; }
.stApp a { color: var(--kontur-blue); }

[data-testid="stCaptionContainer"] { color: var(--kontur-muted); }

/* --- Кнопки --- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 10px !important;
    border: 1px solid transparent;
    font-weight: 500;
    padding: 0.5rem 1.1rem;
    transition: background .15s ease, box-shadow .15s ease, transform .05s ease;
    box-shadow: none;
}
.stButton > button:active, .stDownloadButton > button:active { transform: translateY(1px); }
[data-testid="baseButton-primary"],
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background: var(--kontur-blue);
    color: #fff;
}
[data-testid="baseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    background: var(--kontur-blue-press);
}
[data-testid="baseButton-secondary"] {
    background: #fff;
    color: var(--kontur-black);
    border-color: var(--kontur-border);
}
[data-testid="baseButton-secondary"]:hover {
    background: var(--kontur-gray);
    border-color: rgba(34, 34, 34, 0.18);
}

/* --- Поля ввода --- */
.stTextInput input, .stNumberInput input, .stDateInput input,
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
    border-radius: 10px !important;
    background: #fff !important;
    border-color: var(--kontur-border) !important;
}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within, .stTextInput input:focus {
    border-color: var(--kontur-blue) !important;
    box-shadow: 0 0 0 3px rgba(34, 145, 255, 0.15) !important;
}

/* --- Карточки-метрики --- */
[data-testid="stMetric"] {
    background: #fff;
    border: 1px solid var(--kontur-border);
    border-radius: 16px;
    padding: 18px 20px;
    box-shadow: 0 2px 10px rgba(34, 34, 34, 0.04);
}
[data-testid="stMetricLabel"] { color: var(--kontur-muted); font-weight: 500; }
[data-testid="stMetricValue"] { color: var(--kontur-black); font-weight: 600; }

/* --- Таблицы --- */
[data-testid="stDataFrame"], [data-testid="stTable"] {
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid var(--kontur-border);
    background: #fff;
}

/* --- Плашки, экспандеры, формы --- */
[data-testid="stAlert"] { border-radius: 14px; border: none; }
[data-testid="stExpander"] {
    border: 1px solid var(--kontur-border);
    border-radius: 14px;
    overflow: hidden;
    background: #fff;
}
[data-testid="stForm"] {
    background: #fff;
    border: 1px solid var(--kontur-border);
    border-radius: 18px;
    padding: 1.5rem;
    box-shadow: 0 4px 20px rgba(34, 34, 34, 0.06);
}
hr { border-color: var(--kontur-border); }

/* --- Сайдбар --- */
[data-testid="stSidebar"] {
    background: #fff;
    border-right: 1px solid var(--kontur-border);
}
[data-testid="stSidebar"] hr { border-color: var(--kontur-border); }

/* --- Вкладки --- */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--kontur-border); }
.stTabs [data-baseweb="tab"] { border-radius: 10px 10px 0 0; font-weight: 500; }

/* --- Вертикальное меню-радио --- */
div[role="radiogroup"] label {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 12px;
    width: 100%;
    transition: background .15s ease;
}
div[role="radiogroup"] label:hover { background: rgba(34, 34, 34, 0.05); }
div[role="radiogroup"] label:has(input:checked) { background: #E9F2FF; }
div[role="radiogroup"] label:has(input:checked) p {
    color: var(--kontur-blue-dark) !important;
    font-weight: 500;
}
</style>
"""


def inject_theme() -> None:
    """Подключает фирменный стиль Контура (шрифт, палитра, формы)."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
