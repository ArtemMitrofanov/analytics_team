"""ui/theme.py — обратная совместимость.

Актуальная тема оформления живёт в :mod:`ui.bento` (Bento / Glassmorphism).
Модуль оставлен как тонкая обёртка, чтобы существующие импорты
``from ui.theme import inject_theme`` продолжали работать.
"""
from ui.bento import (
    active_theme_mode,
    inject_theme,
    render_theme_toggle,
)

__all__ = ["active_theme_mode", "inject_theme", "render_theme_toggle"]
