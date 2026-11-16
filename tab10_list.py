"""목록 탭: srnch_members를 읽기 전용으로 표시."""

from __future__ import annotations

import streamlit as st
from supabase import create_client

PAGE_SIZE = 15

# 화면 컬럼 순서. 키는 DB 컬럼, 값은 표시명.
VISIBLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("name", "이름"),
    ("name_distinct", "이름구분"),
    ("gender", "성별"),
    ("children_group", "어린이 조직"),
    ("birth_date", "생년월일"),
    ("age", "나이"),
    ("mobile", "휴대전화"),
    ("household_head", "세대주"),
    ("jibeon_address", "지번주소"),
)

COLUMN_WIDTHS = {
    "이름": 90,
    "이름구분": 80,
    "성별": 60,
    "어린이 조직": 240,
    "생년월일": 110,
    "나이": 60,
    "휴대전화": 130,
    "세대주": 90,
    "지번주소": 280,
}


def _secret(name: str) -> str:
    try:
        value = st.secrets[name]
    except Exception as exc:  # noqa: BLE001
        raise KeyError(f"secrets에 '{name}' 이(가) 없습니다.") from exc
    text = str(value).strip()
    if not text:
        raise ValueError(f"secrets '{name}' 값이 비어 있습니다.")
    return text


def _supabase_url(project: str) -> str:
    project = project.strip().rstrip("/")
    if project.startswith("http://") or project.startswith("https://"):
        return project
    return f"https://{project}.supabase.co"


def _load_page(page: int) -> tuple[list[dict], int]:
    client = create_client(
        _supabase_url(_secret("SUPABASE_PROJECT")),
        _secret("SUPABASE_KEY"),
    )
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE - 1
    columns = ",".join(key for key, _label in VISIBLE_COLUMNS)
    response = (
        client.table("srnch_members")
        .select(columns, count="exact")
        .order("name")
        .order("id")
        .range(start, end)
        .execute()
    )
    rows = response.data or []
    total = int(response.count or 0)
    return rows, total


def _to_display_rows(rows: list[dict]) -> list[dict]:
    display: list[dict] = []
    for row in rows:
        item = {}
        for key, label in VISIBLE_COLUMNS:
            value = row.get(key)
            item[label] = "" if value is None else value
        display.append(item)
    return display


def render() -> None:
    st.subheader("목록")

    st.markdown(
        """
        <style>
        div[data-testid="stDataFrame"] {
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        @media (max-width: 900px) {
            div[data-testid="stDataFrame"] [data-testid="glideDataEditor"],
            div[data-testid="stDataFrame"] > div {
                min-width: 1140px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "member_page" not in st.session_state:
        st.session_state.member_page = 0

    try:
        rows, total = _load_page(int(st.session_state.member_page))
    except Exception as exc:  # noqa: BLE001
        st.error(f"회원 목록을 불러오지 못했습니다: {exc}")
        return

    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if st.session_state.member_page > page_count - 1:
        st.session_state.member_page = page_count - 1
        rows, total = _load_page(int(st.session_state.member_page))

    page = int(st.session_state.member_page)
    st.caption(f"총 {total}건 · {page + 1}/{page_count}페이지 · {PAGE_SIZE}건씩")

    if total == 0:
        st.info("표시할 회원이 없습니다.")
        return

    st.dataframe(
        _to_display_rows(rows),
        hide_index=True,
        use_container_width=True,
        column_order=[label for _key, label in VISIBLE_COLUMNS],
        column_config={
            label: st.column_config.TextColumn(label, width=COLUMN_WIDTHS[label])
            for _key, label in VISIBLE_COLUMNS
        },
    )

    prev_col, page_col, next_col = st.columns([1, 2, 1])
    with prev_col:
        if st.button("이전", disabled=page <= 0, use_container_width=True):
            st.session_state.member_page = page - 1
            st.rerun()
    with page_col:
        st.markdown(
            f"<div style='text-align:center;padding-top:0.35rem;'>{page + 1} / {page_count}</div>",
            unsafe_allow_html=True,
        )
    with next_col:
        if st.button("다음", disabled=page >= page_count - 1, use_container_width=True):
            st.session_state.member_page = page + 1
            st.rerun()
