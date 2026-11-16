"""목록 탭: srnch_members를 읽기 전용으로 표시."""

from __future__ import annotations

import streamlit as st
from openai import OpenAI
from supabase import create_client

PAGE_SIZE = 15

# 화면 컬럼 순서. 키는 DB 컬럼, 값은 표시명.
VISIBLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("name", "이름"),
    ("name_distinct", "구분"),
    ("gender", "성별"),
    ("children_group", "어린이 조직"),
    ("birth_date", "생년월일"),
    ("age", "나이"),
    ("mobile", "휴대전화"),
    ("household_head", "세대주"),
    ("jibeon_address", "지번주소"),
)

PRE_PROMPT = "현재 데이터 기준으로 답변하고, 간략하게 답변하라."

COLUMN_WIDTHS = {
    "이름": 90,
    "구분": 80,
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


def _supabase():
    return create_client(
        _supabase_url(_secret("SUPABASE_PROJECT")),
        _secret("SUPABASE_KEY"),
    )


def _load_page(page: int) -> tuple[list[dict], int]:
    client = _supabase()
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


def _load_all() -> list[dict]:
    columns = ",".join(key for key, _label in VISIBLE_COLUMNS)
    response = (
        _supabase()
        .table("srnch_members")
        .select(columns)
        .order("name")
        .order("id")
        .limit(2000)
        .execute()
    )
    return response.data or []


def _to_display_rows(rows: list[dict]) -> list[dict]:
    display: list[dict] = []
    for row in rows:
        item = {}
        for key, label in VISIBLE_COLUMNS:
            value = row.get(key)
            item[label] = "" if value is None else value
        display.append(item)
    return display


def _system_prompt(rows: list[dict]) -> str:
    header = "\t".join(label for _key, label in VISIBLE_COLUMNS)
    lines = [header]
    for row in _to_display_rows(rows):
        lines.append("\t".join(str(row[label]) for _key, label in VISIBLE_COLUMNS))
    return f"{PRE_PROMPT}\n\n[현재 데이터]\n" + "\n".join(lines)


def _ask_openai(api_key: str, system: str, history: list[dict[str, str]]) -> str:
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[{"role": "system", "content": system}, *history],
    )
    return (response.choices[0].message.content or "").strip()


def _render_chat() -> None:
    st.divider()
    try:
        api_key = _secret("openai_api_key")
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return

    if "member_messages" not in st.session_state:
        st.session_state.member_messages = []

    for message in st.session_state.member_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("회원 데이터에 대해 질문하세요")
    if not prompt:
        return

    st.session_state.member_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        answer = _ask_openai(api_key, _system_prompt(_load_all()), st.session_state.member_messages)
    except Exception as exc:  # noqa: BLE001
        st.error(f"답변을 받지 못했습니다: {exc}")
        return

    st.session_state.member_messages.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)


def render() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stDataFrame"] {
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        .member-pager {
            text-align: left;
            font-size: 0.78rem;
            line-height: 1.2;
            color: #666;
            margin: 0 0 0.35rem 0;
        }
        .member-pager a {
            color: #333;
            text-decoration: none;
        }
        .member-pager .page-no {
            margin: 0 0.45rem;
        }
        .member-pager .muted {
            color: #bbb;
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

    raw_page = st.query_params.get("member_page", "0")
    try:
        page = max(0, int(raw_page))
    except (TypeError, ValueError):
        page = 0

    try:
        rows, total = _load_page(page)
    except Exception as exc:  # noqa: BLE001
        st.error(f"회원 목록을 불러오지 못했습니다: {exc}")
        return

    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page > page_count - 1:
        page = page_count - 1
        rows, total = _load_page(page)

    st.caption(f"총 {total}건")
    if total == 0:
        st.info("표시할 회원이 없습니다.")
        _render_chat()
        return

    prev_html = (
        '<span class="muted">이전</span>'
        if page <= 0
        else f'<a href="?member_page={page - 1}">이전</a>'
    )
    next_html = (
        '<span class="muted">다음</span>'
        if page >= page_count - 1
        else f'<a href="?member_page={page + 1}">다음</a>'
    )
    st.markdown(
        (
            '<div class="member-pager">'
            f"{prev_html}"
            f'<span class="page-no">{page + 1} / {page_count}</span>'
            f"{next_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

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
    _render_chat()
