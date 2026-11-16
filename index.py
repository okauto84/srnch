"""새꿈이 — Streamlit 원프레임 진입점."""

from __future__ import annotations

import streamlit as st

import tab10_list
import tab11_anly
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


def _admin_password_ok() -> bool:
    """ADMIN_PW와 입력값이 일치하면 관리 화면 접근을 허용한다."""
    if st.session_state.get("admin_unlocked"):
        return True

    try:
        expected = str(st.secrets["ADMIN_PW"]).strip()
    except Exception:  # noqa: BLE001
        st.error("secrets에 ADMIN_PW가 필요합니다.")
        return False

    if not expected:
        st.error("secrets의 ADMIN_PW 값이 비어 있습니다.")
        return False

    entered = st.text_input(
        "관리자 비밀번호",
        type="password",
        key="admin_pw_input",
    )
    if st.button("확인", key="admin_pw_submit"):
        if entered == expected:
            st.session_state["admin_unlocked"] = True
            st.rerun()
        st.error("비밀번호가 올바르지 않습니다.")
    return False


# 상단 메뉴바: 왼쪽 제목
st.markdown("### 새꿈이")

# 메뉴 탭 + 하단 콘텐츠 영역
tab_list, tab_anly, tab_admin = st.tabs(["목록", "통계", "ADMIN"])

with tab_list:
    tab10_list.render()

with tab_anly:
    tab11_anly.render()

with tab_admin:
    if _admin_password_ok():
        tab90_admin.render()
