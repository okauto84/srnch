"""목록 탭: srnch_members 조회, 조직 구분 편집."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from supabase import create_client

VISIBLE_ROWS = 10
GRID_ROW_HEIGHT = 35
YEAR_OPTIONS = (2026, 2027)

# 화면 컬럼 순서. 키는 DB 컬럼, 값은 표시명.
VISIBLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("name", "이름"),
    ("name_distinct", "구분"),
    ("gender", "성별"),
    ("part", "부"),
    ("grade", "학년"),
    ("class", "반"),
    ("teacher_name", "담임 선생님"),
    ("birth_date", "생년월일"),
    ("age", "나이"),
    ("mobile", "휴대전화"),
    ("household_head", "세대주"),
    ("jibeon_address", "지번주소"),
)
PRE_PROMPT = """# 역할
저는 어린이를 교육하는 교사로써, 학생 명단을 보고 한국어로 답변하는 선생님.

# 답변 규칙
- 모든 대화와 후속 질문에서 항상 아래 members 배열을 참고하고, 필요한 경우 너의 지식도 포함하여 답한다.
- 현재 데이터 기준으로 친절하게 답변하라.
- 근거는 members 배열뿐이다. 배열에 없는 사실은 "데이터에 없습니다"라고 답한다.
- 인원과 조건 검색은 members의 필드를 직접 세고 비교한다.
- 학생을 지칭할 때는 반드시 `이름구분(부-학년-반)` 형식으로 쓴다. 예: 고승아A(2-1-13)
- 여러 명이면 그 형식으로 나열한다.

# 필드
- members 각 행은 srnch_members의 모든 컬럼을 포함한다.
- year와 part-grade-class로 만든 조직 키 기준으로 조인한 srnch_teacher 행은 teachers 배열에 모두 넣는다.
- teacher_name은 조인된 담임 이름을 이어 붙인 표시용 값이다.
- name: 회원 이름
- name_distinct: 동명이인 구분 한 글자. 없으면 빈 문자열
- part, grade, class: 부, 학년, 반 숫자. 예: 2, 2, 11
- children_group_div: part-grade-class를 이은 표시 값. 예: `2-2-11`
- children_group: "유년-유년2부-2학년-11반" 형태의 조직 경로. 화면 그리드에는 보이지 않는다.

# members
{members}
"""

_ORG_DIV_RE = re.compile(r"^(\d+)-(\d+)-(\d+)$")
_ORG_CLASS_SPAN = 30
_ORG_BOARD = components.declare_component(
    "org_board",
    path=str(Path(__file__).resolve().parent / "components" / "org_board"),
)

COLUMN_WIDTHS = {
    "이름": 90,
    "구분": 48,
    "성별": 48,
    "부": 56,
    "학년": 56,
    "반": 56,
    "담임 선생님": 90,
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


def _teachers_by_group(client, year: int) -> dict[str, list[dict]]:
    """year, part, grade, class 기준 srnch_teacher 전체 행."""
    response = (
        client.table("srnch_teacher")
        .select("*")
        .eq("year", year)
        .limit(2000)
        .execute()
    )
    grouped: dict[str, list[dict]] = {}
    for row in response.data or []:
        part = _as_int(row.get("part"))
        grade = _as_int(row.get("grade"))
        klass = _as_int(row.get("class"))
        if part is None or grade is None or klass is None:
            continue
        grouped.setdefault(f"{part}-{grade}-{klass}", []).append(row)
    return grouped


def _teacher_display_name(teachers: list[dict]) -> str:
    names = sorted(
        {
            str(row.get("teacher_name") or "").strip()
            for row in teachers
            if str(row.get("teacher_name") or "").strip()
        }
    )
    return ", ".join(names)


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_members(url: str, key: str, year: int) -> list[dict]:
    """srnch_members 전체와, year·part-grade-class로 조인한 srnch_teacher 전체를 붙인다."""
    client = create_client(url, key)
    response = (
        client.table("srnch_members")
        .select("*")
        .eq("year", year)
        .order("part", nullsfirst=False)
        .order("grade", nullsfirst=False)
        .order("class", nullsfirst=False)
        .order("name", nullsfirst=False)
        .limit(2000)
        .execute()
    )
    teachers_by_group = _teachers_by_group(client, year)
    rows = response.data or []
    for row in rows:
        row["children_group_div"] = _org_div_text(row)
        group_div = row["children_group_div"]
        teachers = teachers_by_group.get(group_div, [])
        row["teachers"] = teachers
        row["teacher_name"] = _teacher_display_name(teachers)
    rows.sort(key=_grid_sort_key)
    return rows


def _grid_sort_key(row: dict) -> tuple:
    """부, 학년, 반 오름차순. 비어 있으면 뒤로 보내고, 같은 반은 이름순이다."""
    part = _as_int(row.get("part"))
    grade = _as_int(row.get("grade"))
    klass = _as_int(row.get("class"))
    name = str(row.get("name") or "").strip()
    if part is None or grade is None or klass is None:
        return (True, part or 0, grade or 0, klass or 0, name)
    return (False, part, grade, klass, name)


def clear_members_cache() -> None:
    """목록·챗봇용 members 캐시를 비운다."""
    _fetch_members.clear()


def _load_indexed(year: int, *, force_refresh: bool = False) -> list[dict]:
    """그리드와 같은 정렬(조직, 이름)로 해당 연도 회원을 읽는다."""
    if force_refresh:
        clear_members_cache()
    return _fetch_members(
        _supabase_url(_secret("SUPABASE_PROJECT")),
        _secret("SUPABASE_KEY"),
        year,
    )


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
    """그리드/챗봇용 members에 srnch_members·srnch_teacher 조인 결과를 모두 넣는다."""
    payload: list[dict] = []
    for row in rows:
        item = {}
        for key, value in row.items():
            item[key] = "" if value is None else value
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


def _members_json(rows: list[dict]) -> str:
    return json.dumps(_prompt_rows(rows), ensure_ascii=False, indent=2, default=str)


def _api_messages(rows: list[dict], history: list[dict[str, str]]) -> list[dict[str, str]]:
    """화면에 보이는 대화와 달리, 모델에는 매 질문마다 members를 붙인다."""
    members = _members_json(rows)
    messages = [{"role": "system", "content": PRE_PROMPT.format(members=members)}]
    for message in history:
        content = message["content"]
        if message["role"] == "user":
            content = f"{content}\n\n아래 members만 참고해서 답하라.\n{members}"
        messages.append({"role": message["role"], "content": content})
    return messages


def _ask_openai(api_key: str, rows: list[dict], history: list[dict[str, str]]) -> str:
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-6.1-terra",
        reasoning_effort="none",
        temperature=0.2,
        messages=_api_messages(rows, history),
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
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        st.markdown('<span class="member-answer"></span>', unsafe_allow_html=True)
        pending = st.empty()
        with pending.container():
            st.markdown(
                """
                <div class="member-chat-wait" role="status">
                    <span class="member-chat-wait-spin" aria-hidden="true"></span>
                    <span>답변을 작성 중...</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.spinner("답변을 작성 중...", show_time=True):
                try:
                    answer = _ask_openai(api_key, members, st.session_state.member_messages)
                except Exception as exc:  # noqa: BLE001
                    st.session_state.member_chat_error = f"답변을 받지 못했습니다: {exc}"
                    st.rerun()
        answer = _format_member_mentions(answer, members)
        pending.markdown(answer)

    st.session_state.member_messages.append({"role": "assistant", "content": answer})
    st.rerun()


def _as_int(value: object) -> int | None:
    try:
        if isinstance(value, bool) or value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _org_div_text(row: dict) -> str:
    """part, grade, class를 화면용 부-학년-반 문자열로 만든다."""
    part = _as_int(row.get("part"))
    grade = _as_int(row.get("grade"))
    klass = _as_int(row.get("class"))
    if part is None or grade is None or klass is None:
        return ""
    return f"{part}-{grade}-{klass}"


def _parse_org_div(value: object) -> tuple[int, int, int] | None:
    match = _ORG_DIV_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    dept, grade, klass = (int(part) for part in match.groups())
    if not (1 <= dept <= 30 and 1 <= grade <= 30 and 1 <= klass <= 60):
        return None
    return dept, grade, klass


def _format_children_group(template: str, dept: int, grade: int, klass: int) -> str:
    """'03.유년 - 유년1부 - 2학년 - 05반' 형태에서 부·학년·반 숫자만 바꾼다."""
    text = (template or "").strip()
    dept_text = f"유년{dept}부"
    grade_text = f"{grade}학년"
    if not re.search(r"유년\s*\d+\s*부", text):
        return f"{dept_text} - {grade_text} - {klass:02d}반"
    width = 2
    found = re.search(r"(\d+)\s*반", text)
    if found:
        width = max(len(found.group(1)), len(str(klass)))
    klass_text = f"{str(klass).zfill(width)}반"
    text = re.sub(r"유년\s*\d+\s*부", dept_text, text, count=1)
    text = re.sub(r"\d+\s*학년", grade_text, text, count=1)
    text = re.sub(r"\d+\s*반", lambda _match: klass_text, text, count=1)
    return text


def _class_columns(klasses: set[int]) -> list[int]:
    if not klasses:
        return []
    highest = max(klasses)
    if highest <= _ORG_CLASS_SPAN:
        return list(range(1, highest + 1))
    return sorted(klasses)


def _org_spec(year: int, rows: list[dict]) -> dict | None:
    """부-학년-반으로 묶인 회원만 조직 구분 데이터로 만든다."""
    members: list[dict] = []
    seen: set[int] = set()
    grades_by_dept: dict[int, set[int]] = {}
    klasses: set[int] = set()
    for row in rows:
        parsed = _parse_org_div(_org_div_text(row))
        member_id = _as_int(row.get("id"))
        if parsed is None or member_id is None or member_id in seen:
            continue
        label = f"{str(row.get('name') or '').strip()}{str(row.get('name_distinct') or '').strip()}"
        if not label:
            continue
        dept, grade, klass = parsed
        seen.add(member_id)
        members.append(
            {
                "id": member_id,
                "label": label,
                "dept": dept,
                "grade": grade,
                "klass": klass,
            }
        )
        grades_by_dept.setdefault(dept, set()).add(grade)
        klasses.add(klass)
    if not members:
        return None
    members.sort(key=lambda item: (item["dept"], item["grade"], item["klass"], item["label"], item["id"]))
    teachers: dict[tuple[int, int, int], str] = {}
    for row in rows:
        parsed = _parse_org_div(_org_div_text(row))
        if parsed is None:
            continue
        name = str(row.get("teacher_name") or "").strip()
        if name:
            teachers[parsed] = name
    return {
        "year": int(year),
        "classes": _class_columns(klasses),
        "depts": [
            {"dept": dept, "grades": sorted(grades)}
            for dept, grades in sorted(grades_by_dept.items())
        ],
        "members": members,
        "teachers": [
            {"dept": dept, "grade": grade, "klass": klass, "name": name}
            for (dept, grade, klass), name in sorted(teachers.items())
        ],
    }


def _org_signature(year: int, spec: dict) -> str:
    parts = [f"{item['id']}:{item['dept']}-{item['grade']}-{item['klass']}" for item in spec["members"]]
    teacher_parts = [
        f"{item['dept']}-{item['grade']}-{item['klass']}:{item['name']}"
        for item in spec.get("teachers") or []
    ]
    raw = f"{year}|{'|'.join(parts)}|{'|'.join(teacher_parts)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _chunks(items: list[int], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _apply_org_save(year: int, rows: list[dict], event: dict) -> tuple[int, int]:
    """메모리에 쌓인 반 이동·삭제를 srnch_members에 반영한다."""
    by_id: dict[int, dict] = {}
    template = ""
    for row in rows:
        member_id = _as_int(row.get("id"))
        if member_id is None:
            continue
        by_id[member_id] = row
        if not template and str(row.get("children_group") or "").strip():
            template = str(row.get("children_group") or "").strip()

    moves_in = event.get("moves") or []
    deletes_in = event.get("deletes") or []
    if not isinstance(moves_in, list) or not isinstance(deletes_in, list):
        raise ValueError("저장 데이터 형식이 올바르지 않습니다.")
    if len(moves_in) > 2000 or len(deletes_in) > 2000:
        raise ValueError("한 번에 저장할 수 있는 건수를 넘었습니다.")

    delete_ids: list[int] = []
    for raw in deletes_in:
        member_id = _as_int(raw)
        if member_id is None or member_id not in by_id:
            raise ValueError("삭제할 회원을 찾지 못했습니다.")
        if member_id not in delete_ids:
            delete_ids.append(member_id)
    delete_set = set(delete_ids)

    planned: list[tuple[int, int, int, int, str]] = []
    for raw in moves_in:
        if not isinstance(raw, dict):
            raise ValueError("이동 데이터가 올바르지 않습니다.")
        member_id = _as_int(raw.get("id"))
        dept = _as_int(raw.get("dept"))
        grade = _as_int(raw.get("grade"))
        klass = _as_int(raw.get("klass"))
        if member_id is None or member_id not in by_id or member_id in delete_set:
            continue
        if dept is None or grade is None or klass is None:
            raise ValueError("이동할 반 정보가 올바르지 않습니다.")
        if not (1 <= dept <= 30 and 1 <= grade <= 30 and 1 <= klass <= 60):
            raise ValueError("이동할 반 정보가 올바르지 않습니다.")
        source = str(by_id[member_id].get("children_group") or template)
        group = _format_children_group(source, dept, grade, klass)
        if _parse_org_div(_org_div_text(by_id[member_id])) == (dept, grade, klass) and group == source:
            continue
        planned.append((member_id, dept, grade, klass, group))

    client = create_client(
        _supabase_url(_secret("SUPABASE_PROJECT")),
        _secret("SUPABASE_KEY"),
    )
    today = date.today().isoformat()
    for member_id, dept, grade, klass, group in planned:
        (
            client.table("srnch_members")
            .update(
                {
                    "part": dept,
                    "grade": grade,
                    "class": klass,
                    "children_group": group,
                    "updated_at": today,
                }
            )
            .eq("id", member_id)
            .eq("year", year)
            .execute()
        )
    for chunk in _chunks(delete_ids, 200):
        client.table("srnch_members").delete().in_("id", chunk).eq("year", year).execute()
    return len(planned), len(delete_ids)


_MEMBER_ADD_KEYS = (
    "member_add_name",
    "member_add_distinct",
    "member_add_gender",
    "member_add_part",
    "member_add_grade",
    "member_add_class",
)


def _next_member_id(client) -> int:
    response = (
        client.table("srnch_members")
        .select("id")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return 1
    current = _as_int(rows[0].get("id"))
    return (current or 0) + 1


def _member_client():
    return create_client(
        _supabase_url(_secret("SUPABASE_PROJECT")),
        _secret("SUPABASE_KEY"),
    )


def _children_group_path(dept: int, grade: int, klass: int) -> str:
    """조직 번호를 어린이 조직 경로로 바꾼다.

    1-2-4 → 유년-유년1부-2학년-04반
    2-2-11 → 유년-유년2부-2학년-11반
    """
    return f"유년-유년{dept}부-{grade}학년-{klass:02d}반"


def _member_org(part_text: str, grade_text: str, class_text: str) -> tuple[int, int, int]:
    """부, 학년, 반 입력값을 조직 번호로 읽는다."""
    parsed = _parse_org_div(f"{part_text.strip()}-{grade_text.strip()}-{class_text.strip()}")
    if parsed is None:
        raise ValueError("부, 학년, 반은 숫자로 입력하세요. 부는 1–30, 학년은 1–30, 반은 1–60입니다.")
    return parsed


def _member_payload(
    name: str,
    distinct: str,
    gender: str,
    part: int,
    grade: int,
    klass: int,
) -> dict:
    return {
        "name": name,
        "name_distinct": distinct or None,
        "gender": gender or None,
        "part": part,
        "grade": grade,
        "class": klass,
        "children_group": _children_group_path(part, grade, klass),
        "updated_at": date.today().isoformat(),
    }


def _insert_member(
    year: int,
    name: str,
    distinct: str,
    gender: str,
    part: int,
    grade: int,
    klass: int,
) -> None:
    """이름, 구분, 성별, 부, 학년, 반을 선택 연도의 srnch_members에 추가한다."""
    client = _member_client()
    today = date.today().isoformat()
    payload = _member_payload(name, distinct, gender, part, grade, klass)
    payload["id"] = _next_member_id(client)
    payload["year"] = int(year)
    payload["created_at"] = today
    client.table("srnch_members").insert(payload).execute()


def _update_member(
    year: int,
    member_id: int,
    name: str,
    distinct: str,
    gender: str,
    part: int,
    grade: int,
    klass: int,
) -> None:
    """선택한 회원 한 명의 이름, 구분, 성별, 부, 학년, 반을 고친다."""
    payload = _member_payload(name, distinct, gender, part, grade, klass)
    response = (
        _member_client()
        .table("srnch_members")
        .update(payload)
        .eq("id", member_id)
        .eq("year", int(year))
        .execute()
    )
    if not response.data:
        raise LookupError("수정할 회원을 찾지 못했습니다.")


def _delete_member(year: int, member_id: int) -> None:
    """선택한 회원 한 명을 srnch_members에서 지운다."""
    response = (
        _member_client()
        .table("srnch_members")
        .delete()
        .eq("id", member_id)
        .eq("year", int(year))
        .execute()
    )
    if not response.data:
        raise LookupError("삭제할 회원을 찾지 못했습니다.")


def _field_text(value: object) -> str:
    return "" if value is None else str(value)


def _apply_member_form() -> None:
    """선택 행을 입력 칸이 그려지기 전에 반영한다."""
    if st.session_state.pop("member_add_clear", False):
        for key in _MEMBER_ADD_KEYS:
            st.session_state[key] = ""
        st.session_state.pop("member_selected_id", None)
        st.session_state.pop("member_loaded_id", None)
        return
    fill = st.session_state.pop("member_pending_fill", None)
    if not fill:
        return
    st.session_state["member_add_name"] = fill["name"]
    st.session_state["member_add_distinct"] = fill["distinct"]
    st.session_state["member_add_gender"] = fill["gender"]
    st.session_state["member_add_part"] = fill["part"]
    st.session_state["member_add_grade"] = fill["grade"]
    st.session_state["member_add_class"] = fill["class"]
    st.session_state["member_selected_id"] = fill["id"]


def _queue_member_selection(rows: list[dict], selected: list[int]) -> None:
    """고른 행이 바뀌면 입력 칸에 넣기 위해 한 번 더 그린다."""
    if st.session_state.pop("member_ignore_selection", False):
        return
    if not selected:
        return
    index = selected[0]
    if index < 0 or index >= len(rows):
        return
    row = rows[index]
    member_id = _as_int(row.get("id"))
    if member_id is None or member_id == st.session_state.get("member_loaded_id"):
        return
    st.session_state["member_loaded_id"] = member_id
    st.session_state["member_pending_fill"] = {
        "id": member_id,
        "name": _field_text(row.get("name")).strip(),
        "distinct": _field_text(row.get("name_distinct")).strip(),
        "gender": _field_text(row.get("gender")).strip(),
        "part": "" if _as_int(row.get("part")) is None else str(_as_int(row.get("part"))),
        "grade": "" if _as_int(row.get("grade")) is None else str(_as_int(row.get("grade"))),
        "class": "" if _as_int(row.get("class")) is None else str(_as_int(row.get("class"))),
    }
    st.rerun()


def _render_member_add(year: int) -> None:
    """그리드와 조직 구분 사이의 회원 입력."""
    _apply_member_form()
    added = st.session_state.pop("member_added_msg", "")
    deleted_msg = st.session_state.pop("member_deleted_msg", "")
    if added:
        st.success(added)
    if deleted_msg:
        st.success(deleted_msg)

    st.markdown('<span class="member-quick-add"></span>', unsafe_allow_html=True)
    name_col, distinct_col, gender_col, part_col, grade_col, class_col, action_col, _rest = st.columns(
        [1.1, 0.55, 0.55, 0.5, 0.55, 0.5, 1.6, 1.6],
        vertical_alignment="bottom",
    )
    with name_col:
        name = st.text_input("이름", key="member_add_name")
    with distinct_col:
        distinct = st.text_input("구분", key="member_add_distinct")
    with gender_col:
        gender = st.text_input("성별", key="member_add_gender")
    with part_col:
        part_text = st.text_input("부", placeholder="2", key="member_add_part")
    with grade_col:
        grade_text = st.text_input("학년", placeholder="2", key="member_add_grade")
    with class_col:
        class_text = st.text_input("반", placeholder="11", key="member_add_class")
    with action_col:
        delete_col, save_col = st.columns(2, gap="small", vertical_alignment="bottom")
        with delete_col:
            deleted = st.button("삭제", key="member_add_delete_btn", type="secondary")
        with save_col:
            submitted = st.button("저장", key="member_add_save_btn", type="primary")

    if deleted:
        member_id = _as_int(st.session_state.get("member_selected_id"))
        if member_id is None:
            st.error("그리드에서 삭제할 회원을 선택하세요.")
            return
        try:
            _delete_member(int(year), member_id)
        except Exception as exc:  # noqa: BLE001
            st.error(f"삭제하지 못했습니다: {exc}")
            return
        st.session_state["member_add_clear"] = True
        st.session_state["member_grid_generation"] = (
            int(st.session_state.get("member_grid_generation", 0)) + 1
        )
        st.session_state["member_deleted_msg"] = "회원을 삭제했습니다."
        clear_members_cache()
        st.rerun()

    if not submitted:
        return
    name = name.strip()
    distinct = distinct.strip()
    gender = gender.strip()
    part_text = part_text.strip()
    grade_text = grade_text.strip()
    class_text = class_text.strip()
    if not name:
        st.error("이름을 입력하세요.")
        return
    missing = [
        label
        for label, value in (("부", part_text), ("학년", grade_text), ("반", class_text))
        if not value
    ]
    if missing:
        st.error("빈칸이 있습니다: " + ", ".join(missing))
        return
    member_id = _as_int(st.session_state.get("member_selected_id"))
    try:
        part, grade, klass = _member_org(part_text, grade_text, class_text)
        if member_id is None:
            _insert_member(int(year), name, distinct, gender, part, grade, klass)
        else:
            _update_member(int(year), member_id, name, distinct, gender, part, grade, klass)
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장하지 못했습니다: {exc}")
        return
    if member_id is None:
        st.session_state["member_add_clear"] = True
        st.session_state["member_added_msg"] = "회원을 저장했습니다."
    else:
        st.session_state["member_loaded_id"] = member_id
        st.session_state["member_ignore_selection"] = True
        st.session_state["member_added_msg"] = "회원을 수정했습니다."
    clear_members_cache()
    st.rerun()


def _org_saved_text(moved: int, deleted: int) -> str:
    parts: list[str] = []
    if moved:
        parts.append(f"이동 {moved}건")
    if deleted:
        parts.append(f"삭제 {deleted}건")
    detail = ", ".join(parts) if parts else "변경 없음"
    return f"조직 구분을 저장했습니다. {detail}."


def _render_org_board(year: int, rows: list[dict]) -> None:
    """그리드 아래 조직 구분. 이동·삭제는 화면 메모리에 두고 저장 때 DB에 반영한다."""
    st.markdown("**조직 구분**")
    saved = st.session_state.pop("org_saved_msg", "")
    error = st.session_state.pop("org_error_msg", "")
    if saved:
        st.success(saved)
    if error:
        st.error(error)

    spec = _org_spec(year, rows)
    if spec is None:
        st.info("부-학년-반으로 묶을 회원이 없습니다.")
        return

    signature = _org_signature(year, spec)
    reset_token = int(st.session_state.get("org_reset_token", 0))
    spec["sig"] = f"{signature}:{reset_token}"
    spec["error_nonce"] = str(st.session_state.get("org_error_nonce") or "")
    event = _ORG_BOARD(
        spec=spec,
        key=f"org_board_{year}_{signature}_{reset_token}",
        default=None,
    )
    if not isinstance(event, dict) or event.get("action") not in ("save", "reset"):
        return
    nonce = str(event.get("nonce") or "").strip()
    event_year = _as_int(event.get("year"))
    if not nonce or event_year != int(year):
        return
    if nonce == st.session_state.get("org_applied_nonce"):
        return
    if event.get("action") == "reset":
        st.session_state["org_applied_nonce"] = nonce
        st.session_state["org_error_nonce"] = ""
        st.session_state["org_reset_token"] = reset_token + 1
        clear_members_cache()
        st.rerun()
        return

    try:
        with st.spinner("조직 구분을 저장하는 중..."):
            moved, deleted = _apply_org_save(int(year), rows, event)
    except Exception as exc:  # noqa: BLE001
        st.session_state["org_applied_nonce"] = nonce
        st.session_state["org_error_nonce"] = nonce
        st.session_state["org_error_msg"] = f"조직 구분을 저장하지 못했습니다: {exc}"
        st.rerun()
        return

    st.session_state["org_applied_nonce"] = nonce
    st.session_state["org_error_nonce"] = ""
    st.session_state["org_saved_msg"] = _org_saved_text(moved, deleted)
    clear_members_cache()
    st.rerun()


def render(*, force_refresh: bool = False) -> None:
    st.markdown(
        """
        <style>
        [data-testid="stBottom"] {
            position: fixed !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            width: 100% !important;
            z-index: 1000;
            background: var(--background-color);
            padding-bottom: env(safe-area-inset-bottom);
        }
        [data-testid="stChatInput"] textarea {
            min-height: 2rem !important;
            height: 2rem !important;
            padding-top: 0.25rem;
            padding-bottom: 0.25rem;
            line-height: 1.3;
        }
        [data-testid="stChatInput"],
        [data-testid="stBottomBlockContainer"] {
            padding-top: 0.15rem;
            padding-bottom: 0.15rem;
        }
        .block-container {
            padding-bottom: 4.5rem;
        }
        [data-testid="stChatMessage"]:has(.member-answer) {
            margin-left: 1.15rem;
        }
        [data-testid="stChatMessage"]:has(.member-answer) [data-testid="stMarkdown"]:has(.member-answer) {
            display: none;
        }
        .member-chat-wait {
            position: fixed;
            left: 50%;
            bottom: calc(3.5rem + env(safe-area-inset-bottom));
            transform: translateX(-50%);
            z-index: 1001;
            display: flex;
            align-items: center;
            gap: 0.55rem;
            max-width: calc(100% - 2rem);
            padding: 0.5rem 0.95rem;
            border-radius: 999px;
            background: var(--secondary-background-color);
            color: var(--text-color);
            border: 1px solid rgba(128, 128, 128, 0.35);
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
            font-size: 0.95rem;
            line-height: 1.3;
        }
        .member-chat-wait-spin {
            width: 0.95rem;
            height: 0.95rem;
            flex: 0 0 auto;
            border: 2px solid rgba(128, 128, 128, 0.35);
            border-top-color: currentColor;
            border-radius: 50%;
            animation: member-chat-spin 0.8s linear infinite;
        }
        @keyframes member-chat-spin {
            to { transform: rotate(360deg); }
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) {
            gap: 0.15rem;
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stTextInput"] {
            margin-bottom: 0;
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stTextInput"] label {
            font-size: 0.75rem;
            min-height: 0;
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stTextInput"] label p {
            font-size: 0.75rem;
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stTextInput"] input {
            min-height: 1.65rem;
            height: 1.65rem;
            padding-top: 0.1rem;
            padding-bottom: 0.1rem;
            font-size: 0.82rem;
        }
        [data-testid="stHorizontalBlock"]:has([data-testid="stBaseButton-secondary"]):not(:has([data-testid="stHorizontalBlock"])) {
            width: fit-content !important;
            flex: 0 0 auto !important;
            gap: 0.35rem !important;
        }
        [data-testid="stHorizontalBlock"]:has([data-testid="stBaseButton-secondary"]):not(:has([data-testid="stHorizontalBlock"])) > [data-testid="stColumn"] {
            width: auto !important;
            flex: 0 0 auto !important;
            min-width: 0 !important;
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stButton"] button {
            min-height: 0;
            height: auto;
            padding: 8px 28px;
            border-radius: 8px !important;
            font-size: 14px;
            font-weight: 700;
            line-height: 1.2;
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stBaseButton-primary"] {
            border: 0 !important;
            background: #2563eb !important;
            color: #fff !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stBaseButton-primary"]:hover {
            background: #1d4ed8 !important;
            color: #fff !important;
            border: 0 !important;
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stBaseButton-primary"] p {
            font-size: 14px;
            font-weight: 700;
            color: #fff;
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stBaseButton-secondary"] {
            border: 1px solid #b42318 !important;
            background: #fff !important;
            color: #b42318 !important;
            box-shadow: none;
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stBaseButton-secondary"]:hover {
            background: #fff5f5 !important;
            color: #b42318 !important;
            border: 1px solid #b42318 !important;
        }
        [data-testid="stVerticalBlock"]:has(.member-quick-add) [data-testid="stBaseButton-secondary"] p {
            font-size: 14px;
            font-weight: 700;
            color: #b42318;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.get("member_list_year") not in YEAR_OPTIONS:
        st.session_state["member_list_year"] = YEAR_OPTIONS[0]
    year_col, _ = st.columns([1, 5])
    with year_col:
        selected_year = st.selectbox("연도", options=list(YEAR_OPTIONS), key="member_list_year")

    try:
        indexed = _load_indexed(int(selected_year), force_refresh=force_refresh)
    except Exception as exc:  # noqa: BLE001
        st.error(f"회원 목록을 불러오지 못했습니다: {exc}")
        return

    st.caption(f"총 {len(indexed)}건")
    if not indexed:
        st.info(f"{selected_year}년 표시할 회원이 없습니다.")
    else:
        generation = int(st.session_state.get("member_grid_generation", 0))
        selected_state = st.dataframe(
            _to_display_rows(indexed),
            hide_index=True,
            use_container_width=True,
            height=GRID_ROW_HEIGHT * (min(len(indexed), VISIBLE_ROWS) + 1),
            column_order=[label for _key, label in VISIBLE_COLUMNS],
            on_select="rerun",
            selection_mode="single-row",
            key=f"member_grid_{selected_year}_{generation}",
            column_config={
                label: st.column_config.TextColumn(label, width=COLUMN_WIDTHS[label])
                for _key, label in VISIBLE_COLUMNS
            },
        )
        _queue_member_selection(indexed, list(selected_state.selection.rows))
    _render_member_add(int(selected_year))
    if indexed:
        _render_org_board(int(selected_year), indexed)
    _render_chat(indexed)
