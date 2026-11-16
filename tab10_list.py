"""목록 탭: srnch_members를 읽기 전용으로 표시."""

from __future__ import annotations

import json

import pandas as pd
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

PRE_PROMPT = """# 역할
저는 어린이를 교육하는 교사로써, 학생 명단을 보고 한국어로 답하는 선생님.

# 답변 규칙
- 현재 데이터 기준으로 답변하고, 간략하게 답변하라.
- 근거는 아래 members 배열뿐이다. 배열에 없는 사실은 "데이터에 없습니다"라고 답한다.
- 인원과 조건 검색은 members의 필드를 직접 세고 비교한다.
- 여러 명이면 이름만 나열한다.

# 필드
- 이름: 회원 이름
- 구분: 동명이인을 나누는 한 글자. 없으면 빈 문자열
- 성별: 남 또는 여
- 어린이 조직: "03.유년 - 유년1부 - 2학년 - 05반" 형태의 조직 경로
- 생년월일: YYYY-MM-DD
- 나이: 정수
- 휴대전화: 전화번호 문자열
- 세대주: 세대주 이름
- 지번주소: 지번 주소

# members
{members}
"""

COLUMN_WIDTHS = {
    "이름": 90,
    "구분": 48,
    "성별": 48,
    "어린이 조직": 240,
    "생년월일": 110,
    "나이": 48,
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


def _load_indexed() -> list[dict]:
    """그리드와 같은 정렬(이름, id)로 전체 회원을 읽고 위치 번호를 붙인다."""
    columns = "id," + ",".join(key for key, _label in VISIBLE_COLUMNS)
    response = (
        _supabase()
        .table("srnch_members")
        .select(columns)
        .order("name")
        .order("id")
        .limit(2000)
        .execute()
    )
    rows = response.data or []
    for index, row in enumerate(rows):
        row["index"] = index
    return rows


def _focus_id() -> int | None:
    raw = st.query_params.get("focus")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _member_href(member: dict) -> str:
    page = int(member["index"]) // PAGE_SIZE
    return f"?member_page={page}&focus={member['id']}"


def _linkify_members(text: str, members: list[dict]) -> str:
    """답변 안의 회원 이름을 그리드 위치 링크로 바꾼다."""
    grouped: dict[str, list[dict]] = {}
    for member in members:
        name = str(member.get("name") or "").strip()
        if name:
            grouped.setdefault(name, []).append(member)
    if not grouped or not text:
        return text

    occupied = [False] * len(text)
    spans: list[tuple[int, int, str]] = []
    for name in sorted(grouped, key=len, reverse=True):
        start = 0
        while True:
            found = text.find(name, start)
            if found < 0:
                break
            end = found + len(name)
            if not any(occupied[found:end]):
                spans.append((found, end, name))
                for pos in range(found, end):
                    occupied[pos] = True
            start = found + 1

    parts: list[str] = []
    cursor = 0
    for start, end, name in sorted(spans):
        parts.append(text[cursor:start])
        group = grouped[name]
        if len(group) == 1:
            parts.append(f"[{name}]({_member_href(group[0])})")
        else:
            links = []
            for member in group:
                mark = str(member.get("name_distinct") or "").strip() or "구분없음"
                links.append(f"[{name} {mark}]({_member_href(member)})")
            parts.append(" / ".join(links))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def _grid_data(rows: list[dict], focus_id: int | None):
    frame = pd.DataFrame(_to_display_rows(rows))
    if focus_id is None or frame.empty:
        return frame
    ids = [row.get("id") for row in rows]

    def paint(row: pd.Series) -> list[str]:
        if ids[row.name] == focus_id:
            return ["background-color: rgba(255, 214, 102, 0.55)"] * len(row)
        return [""] * len(row)

    return frame.style.apply(paint, axis=1)


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
    members = json.dumps(_to_display_rows(rows), ensure_ascii=False, indent=2, default=str)
    return PRE_PROMPT.format(members=members)


def _ask_openai(api_key: str, system: str, history: list[dict[str, str]]) -> str:
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-6.1-terra",
        reasoning_effort="none",
        temperature=0.2,
        messages=[{"role": "system", "content": system}, *history],
    )
    return (response.choices[0].message.content or "").strip()


def _render_chat(members: list[dict]) -> None:
    try:
        api_key = _secret("openai_api_key")
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return

    if "member_messages" not in st.session_state:
        st.session_state.member_messages = []

    error = st.session_state.pop("member_chat_error", "")
    if error:
        st.error(error)

    for message in st.session_state.member_messages:
        content = message["content"]
        if message["role"] == "assistant":
            content = _linkify_members(content, members)
        with st.chat_message(message["role"]):
            st.markdown(content)
    prompt = st.chat_input("회원 데이터에 대해 질문하세요")

    if not prompt:
        return

    st.session_state.member_messages.append({"role": "user", "content": prompt})
    try:
        answer = _ask_openai(api_key, _system_prompt(members), st.session_state.member_messages)
    except Exception as exc:  # noqa: BLE001
        st.session_state.member_chat_error = f"답변을 받지 못했습니다: {exc}"
        st.rerun()

    st.session_state.member_messages.append({"role": "assistant", "content": answer})
    st.rerun()


def render() -> None:
    st.markdown(
        """
        <style>
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
        .block-container {
            padding-bottom: 4.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    raw_page = st.query_params.get("member_page", "0")
    if isinstance(raw_page, list):
        raw_page = raw_page[0] if raw_page else "0"
    try:
        page = max(0, int(raw_page))
    except (TypeError, ValueError):
        page = 0

    try:
        indexed = _load_indexed()
    except Exception as exc:  # noqa: BLE001
        st.error(f"회원 목록을 불러오지 못했습니다: {exc}")
        return

    focus_id = _focus_id()
    if focus_id is not None:
        matched = next((row for row in indexed if int(row.get("id")) == focus_id), None)
        if matched is not None:
            page = int(matched["index"]) // PAGE_SIZE

    total = len(indexed)
    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page > page_count - 1:
        page = page_count - 1
    rows = indexed[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    st.caption(f"총 {total}건")
    if total == 0:
        st.info("표시할 회원이 없습니다.")
        _render_chat(indexed)
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

    if focus_id is not None and any(int(row.get("id")) == focus_id for row in rows):
        focused = next(row for row in rows if int(row.get("id")) == focus_id)
        st.caption(f"선택: {focused.get('name')}")

    st.dataframe(
        _grid_data(rows, focus_id),
        hide_index=True,
        use_container_width=True,
        column_order=[label for _key, label in VISIBLE_COLUMNS],
        column_config={
            label: st.column_config.TextColumn(label, width=COLUMN_WIDTHS[label])
            for _key, label in VISIBLE_COLUMNS
        },
    )
    _render_chat(indexed)
