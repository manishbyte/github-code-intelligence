"""Simple charts for the evaluation dashboards."""

from __future__ import annotations

from typing import Mapping

import pandas as pd
import streamlit as st


def bar_chart(values: Mapping[str, float | None], *, title: str, as_percent: bool = True) -> None:
    clean = {k: (v or 0.0) * (100 if as_percent else 1) for k, v in values.items()}
    if not clean:
        st.info("No data yet.")
        return
    st.markdown(f"**{title}**")
    st.bar_chart(pd.DataFrame({"value": clean}))
