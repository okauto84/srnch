"""새꿈이 — Streamlit 원프레임 진입점."""

from __future__ import annotations

import streamlit as st

import tab10_list

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
    .top-bar {
        display: flex;
        align-items: center;
        padding: 0.7rem 1rem;
        margin: 0 0 0.25rem 0;
        border: 1px solid #d9d9d9;
        border-bottom: none;
        background: #f7f7f7;
        border-radius: 0.4rem 0.4rem 0 0;
    }
    .brand {
        font-size: 1.35rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #1a1a1a;
        white-space: nowrap;
    }
    .content-frame {
        border: 1px solid #d9d9d9;
        border-radius: 0 0 0.4rem 0.4rem;
        padding: 0.5rem 0.25rem 0.25rem 0.25rem;
        min-height: 70vh;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 상단 메뉴바: 왼쪽 제목
st.markdown('<div class="top-bar"><div class="brand">새꿈이</div></div>', unsafe_allow_html=True)

# 메뉴 탭 + 하단 콘텐츠 영역
tab_list, tab_temp = st.tabs(["목록", "임시"])

with tab_list:
    tab10_list.render()

with tab_temp:
    st.info("임시 탭입니다. 내용을 추가하세요.")
