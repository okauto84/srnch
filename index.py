"""새꿈이 — Streamlit 원프레임 진입점."""

from __future__ import annotations

import streamlit as st

import tab10_list
import tab90_admin

st.set_page_config(
    page_title="새꿈이",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stHeader"] { background: transparent; }
    .block-container {
        padding-top: 0.75rem;
        padding-bottom: 1.5rem;
        max-width: 100%;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 상단 메뉴바: 왼쪽 제목
st.markdown("### 새꿈이")

# 메뉴 탭 + 하단 콘텐츠 영역
tab_list, tab_temp = st.tabs(["목록", "임시"])

with tab_list:
    tab10_list.render()

with tab_temp:
    tab90_admin.render()
