"""담임정보 탭: 담임 정보를 srnch_teacher에 저장·조회한다."""

from __future__ import annotations

import re
from datetime import date

import streamlit as st
from supabase import create_client

GROUP_DIV_RE = re.compile(r"^[0-9]+-[0-9]+-[0-9]+$")
YEAR_OPTIONS = (2026, 2027)
GRID_COLUMNS = (
    ("year", "연도"),
    ("children_group_div", "조직"),
    ("teacher_name", "이름"),
    ("phone", "연락처"),
    ("address", "주소"),
)
COLUMN_WIDTHS = {
    "연도": 80,
    "조직": 110,
    "이름": 110,
    "연락처": 140,
    "주소": 280,
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


def _client():
    return create_client(_supabase_url(_secret("SUPABASE_PROJECT")), _secret("SUPABASE_KEY"))


def _teacher_exists(year: int, children_group_div: str, teacher_name: str) -> bool:
    """같은 연도·조직·이름 행이 이미 있는지 확인한다."""
    response = (
        _client()
        .table("srnch_teacher")
        .select("year")
        .eq("year", year)
        .eq("children_group_div", children_group_div)
        .eq("teacher_name", teacher_name)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def _today() -> str:
    """연-월-일만 저장한다. 시간은 넣지 않는다."""
    return date.today().isoformat()


def _teacher_payload(
    year: int,
    children_group_div: str,
    teacher_name: str,
    phone: str,
    address: str,
) -> dict:
    return {
        "year": year,
        "teacher_name": teacher_name,
        "children_group_div": children_group_div,
        "phone": phone or None,
        "address": address or None,
    }


def _save_teacher(
    year: int,
    children_group_div: str,
    teacher_name: str,
    phone: str,
    address: str,
) -> None:
    """연도, 조직, 이름, 연락처, 주소를 srnch_teacher에 새로 저장한다."""
    today = _today()
    payload = _teacher_payload(year, children_group_div, teacher_name, phone, address)
    payload["created_at"] = today
    payload["updated_at"] = today
    _client().table("srnch_teacher").insert(payload).execute()


def _update_teacher(
    edit_key: dict,
    year: int,
    children_group_div: str,
    teacher_name: str,
    phone: str,
    address: str,
) -> None:
    """선택한 행의 연도·조직·이름·연락처·주소를 고친다."""
    payload = _teacher_payload(year, children_group_div, teacher_name, phone, address)
    payload["updated_at"] = _today()
    response = (
        _client()
        .table("srnch_teacher")
        .update(payload)
        .eq("year", int(edit_key["year"]))
        .eq("children_group_div", edit_key["children_group_div"])
        .eq("teacher_name", edit_key["teacher_name"])
        .execute()
    )
    if response.data is not None and not response.data:
        raise LookupError("선택한 담임 정보를 찾지 못했습니다.")


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_teachers(year: int, _version: int) -> list[dict]:
    response = (
        _client()
        .table("srnch_teacher")
        .select("year,children_group_div,teacher_name,phone,address")
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


def _alert(message: str) -> None:
    st.error(message)
    st.toast(message, icon="⚠️")


def _same_teacher(edit_key: dict | None, year: int, group_text: str, name_text: str) -> bool:
    if not edit_key:
        return False
    return (
        int(edit_key["year"]) == year
        and edit_key["children_group_div"] == group_text
        and edit_key["teacher_name"] == name_text
    )


def _remember_saved(year: int, group_text: str, name_text: str) -> None:
    """방금 저장한 행을 이어서 고칠 수 있게 둔다."""
    st.session_state["teacher_edit_key"] = {
        "year": year,
        "children_group_div": group_text,
        "teacher_name": name_text,
    }
    st.session_state["teacher_loaded_sig"] = (str(year), group_text, name_text)


def _handle_save(
    year_text: str,
    group_text: str,
    name_text: str,
    phone_text: str,
    address_text: str,
) -> int | None:
    year_text = year_text.strip()
    group_text = group_text.strip()
    name_text = name_text.strip()
    phone_text = phone_text.strip()
    address_text = address_text.strip()
    missing = [
        label
        for label, value in (("연도", year_text), ("조직", group_text), ("이름", name_text))
        if not value
    ]
    if missing:
        _alert("빈칸이 있습니다: " + ", ".join(missing))
        return None

    try:
        year = int(year_text)
    except ValueError:
        _alert("연도는 숫자로 입력하세요.")
        return None
    if not 2000 <= year <= 2100:
        _alert("연도는 2000년부터 2100년까지 입력하세요.")
        return None
    if not GROUP_DIV_RE.fullmatch(group_text):
        _alert("조직은 1-1-5 형식으로 입력하세요.")
        return None

    edit_key = st.session_state.get("teacher_edit_key")
    try:
        if edit_key:
            if not _same_teacher(edit_key, year, group_text, name_text) and _teacher_exists(
                year, group_text, name_text
            ):
                _alert(f"이미 같은 데이터가 있습니다: {year} / {group_text} / {name_text}")
                return None
            _update_teacher(edit_key, year, group_text, name_text, phone_text, address_text)
        else:
            if _teacher_exists(year, group_text, name_text):
                _alert(f"이미 같은 데이터가 있습니다: {year} / {group_text} / {name_text}")
                return None
            _save_teacher(year, group_text, name_text, phone_text, address_text)
    except Exception as exc:  # noqa: BLE001
        _alert(f"저장하지 못했습니다: {exc}")
        return None

    _remember_saved(year, group_text, name_text)
    st.session_state["teacher_data_version"] = int(st.session_state.get("teacher_data_version", 0)) + 1
    if year in YEAR_OPTIONS:
        st.session_state["teacher_list_year"] = year
    return year


_INPUT_KEYS = (
    "teacher_input_year",
    "teacher_input_group",
    "teacher_input_name",
    "teacher_input_phone",
    "teacher_input_address",
)


def _apply_form_overrides() -> None:
    """선택 행이나 새로 입력을 위젯이 그려지기 전에 반영한다."""
    if st.session_state.pop("teacher_clear_requested", False):
        for key in _INPUT_KEYS:
            st.session_state[key] = ""
        st.session_state.pop("teacher_edit_key", None)
        st.session_state.pop("teacher_loaded_sig", None)
        st.session_state.pop("teacher_pending_fill", None)
        st.session_state["teacher_grid_generation"] = (
            int(st.session_state.get("teacher_grid_generation", 0)) + 1
        )
        return

    fill = st.session_state.pop("teacher_pending_fill", None)
    if not fill:
        return
    st.session_state["teacher_input_year"] = fill["year"]
    st.session_state["teacher_input_group"] = fill["group"]
    st.session_state["teacher_input_name"] = fill["name"]
    st.session_state["teacher_input_phone"] = fill["phone"]
    st.session_state["teacher_input_address"] = fill["address"]
    st.session_state["teacher_edit_key"] = fill["key"]


def _queue_selected_row(rows: list[dict], selected: list[int]) -> None:
    """고른 행이 바뀌면 입력 칸에 넣기 위해 한 번 더 그린다."""
    if not selected:
        return
    index = selected[0]
    if index < 0 or index >= len(rows):
        return
    row = rows[index]
    year = int(row["year"])
    group = str(row.get("children_group_div") or "")
    name = str(row.get("teacher_name") or "")
    sig = (str(year), group, name)
    if sig == st.session_state.get("teacher_loaded_sig"):
        return
    st.session_state["teacher_loaded_sig"] = sig
    st.session_state["teacher_pending_fill"] = {
        "year": str(year),
        "group": group,
        "name": name,
        "phone": "" if row.get("phone") is None else str(row.get("phone")),
        "address": "" if row.get("address") is None else str(row.get("address")),
        "key": {"year": year, "children_group_div": group, "teacher_name": name},
    }
    st.rerun()


def render() -> None:
    """담임 정보 입력과 연도별 목록."""
    _apply_form_overrides()
    st.markdown("**담임 정보**")
    col_year, col_group, col_name, col_phone = st.columns(
        [1, 1.3, 1.2, 1.6], vertical_alignment="bottom"
    )
    with col_year:
        year_text = st.text_input("연도", key="teacher_input_year")
    with col_group:
        group_text = st.text_input("조직", placeholder="1-1-5", key="teacher_input_group")
    with col_name:
        name_text = st.text_input("이름", key="teacher_input_name")
    with col_phone:
        phone_text = st.text_input("연락처", key="teacher_input_phone")

    col_address, col_new, col_save = st.columns([4.2, 0.95, 0.7], vertical_alignment="bottom")
    with col_address:
        address_text = st.text_input("주소", key="teacher_input_address")
    with col_new:
        clear_clicked = st.button("새로 입력", use_container_width=True, key="teacher_new_btn")
    with col_save:
        submitted = st.button("저장", use_container_width=True, key="teacher_save_btn")

    if clear_clicked:
        st.session_state["teacher_clear_requested"] = True
        st.rerun()

    if submitted:
        saved = _handle_save(year_text, group_text, name_text, phone_text, address_text)
        if saved is not None:
            st.session_state["teacher_saved_msg"] = True
            st.session_state["teacher_grid_generation"] = (
                int(st.session_state.get("teacher_grid_generation", 0)) + 1
            )

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
    st.caption("행을 선택하면 입력 칸에 넣습니다. 수정 후 저장하면 그 행에 반영됩니다.")
    generation = int(st.session_state.get("teacher_grid_generation", 0))
    selected = st.dataframe(
        _to_display_rows(rows),
        hide_index=True,
        use_container_width=True,
        column_order=labels,
        on_select="rerun",
        selection_mode="single-row",
        key=f"teacher_grid_{selected_year}_{generation}",
        column_config={
            label: st.column_config.TextColumn(
                label,
                width=COLUMN_WIDTHS[label],
                alignment="left" if label == "주소" else "center",
            )
            for label in labels
        },
    )
    _queue_selected_row(rows, list(selected.selection.rows))
