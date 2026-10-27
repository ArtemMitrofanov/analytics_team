"""tests/test_bento_ui.py — контракт дизайн-системы Bento."""
import re

from streamlit.testing.v1 import AppTest

from ui.bento import (
    BENTO_COLORS,
    bento_palette,
    kpi_card_html,
    plotly_template,
)


def test_plotly_template_is_transparent() -> None:
    template = plotly_template("dark")
    assert template.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert template.layout.plot_bgcolor == "rgba(0,0,0,0)"


def test_plotly_template_uses_bento_palette_and_font() -> None:
    template = plotly_template("dark")
    assert "Inter" in template.layout.font.family
    assert list(template.layout.colorway) == bento_palette("dark")["series"]
    assert bento_palette("dark")["emerald"] in template.layout.colorway


def test_light_plotly_template_uses_light_palette() -> None:
    template = plotly_template("light")
    assert template.layout.font.color == bento_palette("light")["text"]
    assert list(template.layout.colorway) == bento_palette("light")["series"]
    assert template.layout.paper_bgcolor == "rgba(0,0,0,0)"


def test_light_palette_differs_from_dark() -> None:
    dark = bento_palette("dark")
    light = bento_palette("light")
    assert dark["mode"] == "dark"
    assert light["mode"] == "light"
    assert dark["series"] != light["series"]
    assert BENTO_COLORS["emerald"] == dark["emerald"]


def test_kpi_card_escapes_user_content() -> None:
    html = kpi_card_html(
        title="<script>alert(1)</script>",
        value="<b>42</b>",
        change_pct=1.0,
        trend_direction="up",
        icon_name="activity",
        caption="<img src=x onerror=alert(1)>",
    )
    assert "<script>" not in html
    assert "<b>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;" in html


def test_kpi_card_tone_respects_positive_is_good() -> None:
    growing = kpi_card_html("MTTR", "8 ч", 12.5, "up", "clock")
    assert "bento-kpi__badge--good" in growing

    inverse = kpi_card_html("MTTR", "8 ч", 12.5, "up", "clock", positive_is_good=False)
    assert "bento-kpi__badge--bad" in inverse

    reverse = kpi_card_html("MTTR", "8 ч", -7.0, "down", "clock", positive_is_good=False)
    assert "bento-kpi__badge--good" in reverse


def test_kpi_card_neutral_without_change() -> None:
    html = kpi_card_html("Задач", "120", None, "flat", "layers")
    assert "bento-kpi__badge--neutral" in html
    assert "—" in html


def test_kpi_card_unknown_accent_falls_back() -> None:
    html = kpi_card_html("Задач", "120", 3.0, "up", "layers", accent="hotpink")
    assert "bento-kpi--indigo" in html
    assert "hotpink" not in html


def test_kpi_card_sparkline_requires_two_points() -> None:
    single = kpi_card_html("Задач", "120", 3.0, "up", "layers", sparkline_values=[1])
    assert "bento-kpi__spark" not in single

    series = kpi_card_html(
        "Задач", "120", 3.0, "up", "layers", sparkline_values=[1, 2, 3]
    )
    assert "bento-kpi__spark" in series
    assert "<svg" in series
    assert re.search(r'id="bento-spark-[0-9a-f]{8}"', series)


def test_kpi_card_sparkline_uses_mode_palette() -> None:
    dark = kpi_card_html("Задач", "120", 3.0, "up", "layers", sparkline_values=[1, 2])
    light = kpi_card_html(
        "Задач", "120", 3.0, "up", "layers", sparkline_values=[1, 2], mode="light"
    )
    assert bento_palette("dark")["indigo"] in dark
    assert bento_palette("light")["indigo"] in light


def test_theme_toggle_switches_between_modes() -> None:
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from ui.bento import active_theme_mode, render_theme_toggle\n"
        "render_theme_toggle()\n"
        "st.write(active_theme_mode())\n"
    )
    app.run()

    assert not app.exception
    assert app.markdown[-1].value == "dark"

    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert app.markdown[-1].value == "light"

    app.toggle[0].set_value(False).run()
    assert not app.exception
    assert app.markdown[-1].value == "dark"
