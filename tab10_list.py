"""목록 탭: srnch_members를 읽기 전용으로 표시."""

from __future__ import annotations

import json

import streamlit as st
from openai import OpenAI
from supabase import create_client

VISIBLE_ROWS = 15
GRID_ROW_HEIGHT = 35

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
저는 어린이를 교육하는 교사로써, 학생 명단을 보고 한국어로 답변하는 선생님.

# 답변 규칙
- 현재 데이터 기준으로 친절하게 답변하라.
- 근거는 아래 members 배열뿐이다. 배열에 없는 사실은 "데이터에 없습니다"라고 답한다.
- 인원과 조건 검색은 members의 필드를 직접 세고 비교한다.
- 학생을 지칭할 때는 반드시 `이름구분(어린이 조직 div)` 형식으로 쓴다. 예: 고승아A(2-1-13)
- 여러 명이면 그 형식으로 나열한다.

# 필드
- 이름: 회원 이름
- 구분: 동명이인을 나누는 한 글자. 없으면 빈 문자열
- 어린이 조직 div: `1-2-5`처럼 부-학년-반을 숫자로 줄인 값
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


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_members(url: str, key: str) -> list[dict]:
    """회원 목록을 잠시 보관한다."""
    columns = "id,children_group_div," + ",".join(column for column, _label in VISIBLE_COLUMNS)
    response = (
        create_client(url, key)
        .table("srnch_members")
        .select(columns)
        .order("name")
        .order("id")
        .limit(2000)
        .execute()
    )
    return response.data or []


def _load_indexed() -> list[dict]:
    """그리드와 같은 정렬(이름, id)로 전체 회원을 읽는다."""
    return _fetch_members(_supabase_url(_secret("SUPABASE_PROJECT")), _secret("SUPABASE_KEY"))


def _member_label(member: dict) -> str:
    """고승아A(2-1-13) 형식."""
    name = str(member.get("name") or "").strip()
    mark = str(member.get("name_distinct") or "").strip()
    group_div = str(member.get("children_group_div") or "").strip()
    return f"{name}{mark}({group_div})"


def _format_member_mentions(text: str, members: list[dict]) -> str:
    """답변 속 학생 이름을 이름+구분+(조직 div)로 바꾼다."""
    if not text:
        return text

    grouped: dict[str, list[dict]] = {}
    for member in members:
        name = str(member.get("name") or "").strip()
        if name:
            grouped.setdefault(name, []).append(member)
    if not grouped:
        return text

    occupied = [False] * len(text)

    def occupy(start: int, end: int) -> None:
        for pos in range(start, end):
            occupied[pos] = True

    def is_free(start: int, end: int) -> bool:
        return not any(occupied[start:end])

    labels = {_member_label(member) for group in grouped.values() for member in group}
    for label in sorted(labels, key=len, reverse=True):
        start = 0
        while True:
            found = text.find(label, start)
            if found < 0:
                break
            occupy(found, found + len(label))
            start = found + len(label)

    spans: list[tuple[int, int, str]] = []
    marked = [
        (f"{name}{str(member.get('name_distinct') or '').strip()}", _member_label(member))
        for name, group in grouped.items()
        for member in group
        if str(member.get("name_distinct") or "").strip()
    ]
    for token, label in sorted(marked, key=lambda item: len(item[0]), reverse=True):
        start = 0
        while True:
            found = text.find(token, start)
            if found < 0:
                break
            end = found + len(token)
            if is_free(found, end):
                spans.append((found, end, label))
                occupy(found, end)
            start = end

    for name in sorted(grouped, key=len, reverse=True):
        labels_for_name = [_member_label(member) for member in grouped[name]]
        start = 0
        while True:
            found = text.find(name, start)
            if found < 0:
                break
            end = found + len(name)
            if is_free(found, end):
                spans.append((found, end, ", ".join(labels_for_name)))
                occupy(found, end)
            start = end

    if not spans:
        return text

    parts: list[str] = []
    cursor = 0
    for start, end, label in sorted(spans):
        parts.append(text[cursor:start])
        parts.append(label)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def _prompt_rows(rows: list[dict]) -> list[dict]:
    prompt_columns = VISIBLE_COLUMNS + (("children_group_div", "어린이 조직 div"),)
    payload: list[dict] = []
    for row in rows:
        item = {}
        for key, label in prompt_columns:
            value = row.get(key)
            item[label] = "" if value is None else value
        payload.append(item)
    return payload


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
    members = json.dumps(_prompt_rows(rows), ensure_ascii=False, indent=2, default=str)
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
            content = _format_member_mentions(content, members)
            with st.chat_message("assistant"):
                st.markdown('<span class="member-answer"></span>', unsafe_allow_html=True)
                st.markdown(content)
        else:
            with st.chat_message("user"):
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

    answer = _format_member_mentions(answer, members)
    st.session_state.member_messages.append({"role": "assistant", "content": answer})
    st.rerun()


def render() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stChatInput"] textarea {
            min-height: 2rem !important;
            height: 2rem !important;
            padding-top: 0.25rem;
            padding-bottom: 0.25rem;
            line-height: 1.3;
        }
        [data-testid="stChatInput"],
        [data-testid="stBottom"],
        [data-testid="stBottomBlockContainer"] {
            padding-top: 0.15rem;
            padding-bottom: 0.15rem;
        }
        .block-container {
            padding-bottom: 3.2rem;
        }
        [data-testid="stChatMessage"]:has(.member-answer) {
            margin-left: 1.15rem;
        }
        [data-testid="stChatMessage"]:has(.member-answer) [data-testid="stMarkdown"]:has(.member-answer) {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    try:
        indexed = _load_indexed()
    except Exception as exc:  # noqa: BLE001
        st.error(f"회원 목록을 불러오지 못했습니다: {exc}")
        return

    st.caption(f"총 {len(indexed)}건")
    if not indexed:
        st.info("표시할 회원이 없습니다.")
        _render_chat(indexed)
        return

    st.dataframe(
        _to_display_rows(indexed),
        hide_index=True,
        use_container_width=True,
        height=GRID_ROW_HEIGHT * (min(len(indexed), VISIBLE_ROWS) + 1),
        column_order=[label for _key, label in VISIBLE_COLUMNS],
        column_config={
            label: st.column_config.TextColumn(label, width=COLUMN_WIDTHS[label])
            for _key, label in VISIBLE_COLUMNS
        },
    )
    _render_chat(indexed)
