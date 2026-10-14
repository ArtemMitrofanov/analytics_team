"""Проверка зависимостей при реальном отображении таблицы Streamlit."""
from streamlit.testing.v1 import AppTest


def test_dataframe_renders_with_numpy_and_pyarrow():
    app = AppTest.from_string('''
import numpy as np
import pandas as pd
import streamlit as st
st.dataframe(pd.DataFrame({
    "Статус": ["В разработке"],
    "Дни": np.array([1.5]),
}))
''').run()
    assert not app.exception, [item.message for item in app.exception]
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value.iloc[0]["Дни"] == 1.5
