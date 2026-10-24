"""Проверка зависимостей при реальном отображении таблицы Streamlit."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

_SCRIPT = '''
import numpy as np
import pandas as pd
import streamlit as st

st.dataframe(pd.DataFrame({
    "Статус": ["В разработке"],
    "Дни": np.array([1.5]),
}))
'''


def test_dataframe_renders_with_numpy_and_pyarrow(tmp_path: Path):
    # Пишем исходник сами в UTF-8: AppTest.from_string на Windows сохраняет
    # временный файл в кодировке локали (cp1251), из-за чего кириллица ломается.
    script = tmp_path / "ui_runtime_app.py"
    script.write_text(_SCRIPT, encoding="utf-8")

    app = AppTest.from_file(str(script)).run()

    assert not app.exception, [item.message for item in app.exception]
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value.iloc[0]["Дни"] == 1.5
