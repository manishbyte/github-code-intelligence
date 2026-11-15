"""Recruiter dashboard widgets."""

from __future__ import annotations

from typing import Sequence

import streamlit as st


def metric_row(items: Sequence[tuple[str, str]]) -> None:
    for col, (label, value) in zip(st.columns(len(items)), items):
        col.metric(label, value)
