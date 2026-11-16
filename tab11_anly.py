"""통계 탭: 담임 정보를 srnch_teacher에 저장·조회한다."""

from __future__ import annotations

import re

import streamlit as st
from supabase import create_client

GROUP_DIV_RE = re.compile(r"^[0-9]+-[0-9]+-[0-9]+$")
YEAR_OPTIONS = (2026, 2027)
GRID_COLUMNS = (
    ("year", "연도"),
    ("children_group_div", "조직"),
    ("teacher_name", "이름"),
)


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


def _client():
    return create_client(_supabase_url(_secret("SUPABASE_PROJECT")), _secret("SUPABASE_KEY"))


def _save_teacher(year: int, children_group_div: str, teacher_name: str) -> None:
    """연도, 조직, 이름을 srnch_teacher에 저장한다."""
    (
        _client()
        .table("srnch_teacher")
        .upsert(
            {
                "year": year,
                "teacher_name": teacher_name,
                "children_group_div": children_group_div,
            },
            on_conflict="year,teacher_name,children_group_div",
        )
        .execute()
    )


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_teachers(year: int, _version: int) -> list[dict]:
    response = (
        _client()
        .table("srnch_teacher")
        .select("year,children_group_div,teacher_name")
        .eq("year", year)
        .order("children_group_div")
        .order("teacher_name")
        .execute()
    )
    return response.data or []


def _to_display_rows(rows: list[dict]) -> list[dict]:
    display: list[dict] = []
    for row in rows:
        item = {}
        for key, label in GRID_COLUMNS:
            value = row.get(key)
            item[label] = "" if value is None else str(value)
        display.append(item)
    return display


def _handle_save(year_text: str, group_text: str, name_text: str) -> int | None:
    year_text = year_text.strip()
    group_text = group_text.strip()
    name_text = name_text.strip()
    missing = [
        label
        for label, value in (("연도", year_text), ("조직", group_text), ("이름", name_text))
        if not value
    ]
    if missing:
        st.error("빈칸이 있습니다: " + ", ".join(missing))
        return None

    try:
        year = int(year_text)
    except ValueError:
        st.error("연도는 숫자로 입력하세요.")
        return None
    if not 2000 <= year <= 2100:
        st.error("연도는 2000년부터 2100년까지 입력하세요.")
        return None
    if not GROUP_DIV_RE.fullmatch(group_text):
        st.error("조직은 1-1-5 형식으로 입력하세요.")
        return None

    try:
        _save_teacher(year, group_text, name_text)
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장하지 못했습니다: {exc}")
        return None

    st.session_state["teacher_data_version"] = int(st.session_state.get("teacher_data_version", 0)) + 1
    st.session_state["teacher_list_year"] = year
    return year


def render() -> None:
    """담임 정보 입력과 연도별 목록."""
    st.markdown("**담임 정보**")
    col_year, col_group, col_name, col_save = st.columns([1, 1.4, 1.2, 0.7], vertical_alignment="bottom")
    with col_year:
        year_text = st.text_input("연도", key="teacher_input_year")
    with col_group:
        group_text = st.text_input("조직", placeholder="1-1-5", key="teacher_input_group")
    with col_name:
        name_text = st.text_input("이름", key="teacher_input_name")
    with col_save:
        submitted = st.button("저장", use_container_width=True, key="teacher_save_btn")

    if submitted:
        if _handle_save(year_text, group_text, name_text) is not None:
            st.session_state["teacher_saved_msg"] = True

    if st.session_state.pop("teacher_saved_msg", False):
        st.success("저장했습니다.")

    version = int(st.session_state.get("teacher_data_version", 0))
    if st.session_state.get("teacher_list_year") not in YEAR_OPTIONS:
        st.session_state["teacher_list_year"] = YEAR_OPTIONS[0]

    year_col, _ = st.columns([1, 5])
    with year_col:
        selected_year = st.selectbox(
            "연도",
            options=list(YEAR_OPTIONS),
            key="teacher_list_year",
        )

    try:
        rows = _fetch_teachers(int(selected_year), version)
    except Exception as exc:  # noqa: BLE001
        st.error(f"담임 목록을 불러오지 못했습니다: {exc}")
        return

    if not rows:
        st.info(f"{selected_year}년 담임 정보가 없습니다.")
        return

    labels = [label for _key, label in GRID_COLUMNS]
    st.dataframe(
        _to_display_rows(rows),
        hide_index=True,
        use_container_width=True,
        column_order=labels,
        column_config={
            label: st.column_config.TextColumn(label, alignment="center")
            for label in labels
        },
    )
