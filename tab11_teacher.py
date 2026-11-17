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


# srnch_teacher 기본 키. 이 세 값이 모두 맞을 때만 한 행을 고치거나 지운다.
TEACHER_KEY_FIELDS = ("year", "teacher_name", "children_group_div")
TEACHER_KEY_SELECT = "year,teacher_name,children_group_div"


def _client():
    return create_client(_supabase_url(_secret("SUPABASE_PROJECT")), _secret("SUPABASE_KEY"))


def _make_teacher_key(year: int, teacher_name: str, children_group_div: str) -> dict:
    """기본 키를 정규화한다. 하나라도 비면 거부한다."""
    name = str(teacher_name).strip()
    group = str(children_group_div).strip()
    if not isinstance(year, int):
        year = int(year)
    if not name or not group:
        raise ValueError("담임 키(year, teacher_name, children_group_div)가 완전하지 않습니다.")
    if not GROUP_DIV_RE.fullmatch(group):
        raise ValueError("조직은 1-1-5 형식으로 입력하세요.")
    return {
        "year": year,
        "teacher_name": name,
        "children_group_div": group,
    }


def _as_teacher_key(raw: dict | None) -> dict:
    """세션/선택 값에서 기본 키만 뽑아 검증한다."""
    if not raw:
        raise ValueError("담임 키가 없습니다.")
    missing = [field for field in TEACHER_KEY_FIELDS if raw.get(field) in (None, "")]
    if missing:
        raise ValueError(
            "담임 키가 완전하지 않습니다: " + ", ".join(missing)
        )
    return _make_teacher_key(
        int(raw["year"]),
        str(raw["teacher_name"]),
        str(raw["children_group_div"]),
    )


def _filter_by_teacher_key(query, key: dict):
    """세 키 조건이 모두 있을 때만 필터한다. 다른 행이 걸리지 않게 한다."""
    key = _as_teacher_key(key)
    return (
        query.eq("year", key["year"])
        .eq("teacher_name", key["teacher_name"])
        .eq("children_group_div", key["children_group_div"])
    )


def _require_one_row(rows: list | None, action: str) -> dict:
    if not rows:
        raise LookupError(f"{action}할 담임 정보를 찾지 못했습니다.")
    if len(rows) != 1:
        raise RuntimeError(
            f"{action} 대상이 {len(rows)}건입니다. "
            "year, teacher_name, children_group_div 키가 한 행만 가리켜야 합니다."
        )
    return rows[0]


def _teacher_exists(key: dict) -> bool:
    """같은 기본 키 행이 이미 있는지 확인한다."""
    response = (
        _filter_by_teacher_key(
            _client().table("srnch_teacher").select("year"),
            key,
        )
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
    key = _make_teacher_key(year, teacher_name, children_group_div)
    return {
        **key,
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
    """선택한 행만, 기본 키 세 조건으로 고친다."""
    old_key = _as_teacher_key(edit_key)
    new_key = _make_teacher_key(year, teacher_name, children_group_div)
    if old_key == new_key:
        # 키가 같으면 연락처·주소만 바꿔 다른 행 키를 건드리지 않는다.
        payload = {
            "phone": phone or None,
            "address": address or None,
            "updated_at": _today(),
        }
    else:
        payload = _teacher_payload(year, children_group_div, teacher_name, phone, address)
        payload["updated_at"] = _today()

    response = _filter_by_teacher_key(
        _client().table("srnch_teacher").update(payload),
        old_key,
    ).select(TEACHER_KEY_SELECT).execute()
    _require_one_row(response.data, "수정")


def _delete_teacher(key: dict) -> None:
    """기본 키 세 조건이 모두 같은 한 행만 지운다."""
    key = _as_teacher_key(key)
    response = _filter_by_teacher_key(
        _client().table("srnch_teacher").delete(),
        key,
    ).select(TEACHER_KEY_SELECT).execute()
    _require_one_row(response.data, "삭제")


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


def _same_teacher(edit_key: dict | None, key: dict) -> bool:
    if not edit_key:
        return False
    try:
        return _as_teacher_key(edit_key) == _as_teacher_key(key)
    except (KeyError, TypeError, ValueError):
        return False


def _remember_saved(key: dict) -> None:
    """방금 저장한 행을 이어서 고칠 수 있게 둔다."""
    key = _as_teacher_key(key)
    st.session_state["teacher_edit_key"] = key
    st.session_state["teacher_loaded_sig"] = (
        str(key["year"]),
        key["children_group_div"],
        key["teacher_name"],
    )


def _handle_save(
    year_text: str,
    group_text: str,
    name_text: str,
    phone_text: str,
    address_text: str,
) -> int | None:
    phone_text = phone_text.strip()
    address_text = address_text.strip()
    parsed = _parse_teacher_key(year_text, group_text, name_text)
    if parsed is None:
        return None
    year, group_text, name_text = parsed
    new_key = _make_teacher_key(year, name_text, group_text)

    edit_raw = st.session_state.get("teacher_edit_key")
    try:
        if edit_raw:
            edit_key = _as_teacher_key(edit_raw)
            if not _same_teacher(edit_key, new_key) and _teacher_exists(new_key):
                _alert(
                    "이미 같은 데이터가 있습니다: "
                    f"{new_key['year']} / {new_key['children_group_div']} / {new_key['teacher_name']}"
                )
                return None
            _update_teacher(
                edit_key,
                new_key["year"],
                new_key["children_group_div"],
                new_key["teacher_name"],
                phone_text,
                address_text,
            )
        else:
            if _teacher_exists(new_key):
                _alert(
                    "이미 같은 데이터가 있습니다: "
                    f"{new_key['year']} / {new_key['children_group_div']} / {new_key['teacher_name']}"
                )
                return None
            _save_teacher(
                new_key["year"],
                new_key["children_group_div"],
                new_key["teacher_name"],
                phone_text,
                address_text,
            )
    except Exception as exc:  # noqa: BLE001
        _alert(f"저장하지 못했습니다: {exc}")
        return None

    _remember_saved(new_key)
    return new_key["year"]


_INPUT_KEYS = (
    "teacher_input_year",
    "teacher_input_group",
    "teacher_input_name",
    "teacher_input_phone",
    "teacher_input_address",
)


def _clear_form() -> None:
    """입력 칸과 선택 상태를 비운다."""
    for key in _INPUT_KEYS:
        st.session_state[key] = ""
    st.session_state.pop("teacher_edit_key", None)
    st.session_state.pop("teacher_loaded_sig", None)
    st.session_state.pop("teacher_pending_fill", None)
    st.session_state["teacher_grid_generation"] = (
        int(st.session_state.get("teacher_grid_generation", 0)) + 1
    )


def _refresh_teacher_list(year: int | None = None) -> None:
    """저장·삭제 뒤 캐시를 비우고 그리드가 최신 목록을 다시 읽게 한다."""
    _fetch_teachers.clear()
    st.session_state["teacher_data_version"] = int(st.session_state.get("teacher_data_version", 0)) + 1
    st.session_state["teacher_grid_generation"] = (
        int(st.session_state.get("teacher_grid_generation", 0)) + 1
    )
    if year is not None and year in YEAR_OPTIONS:
        st.session_state["teacher_list_year"] = year


def _parse_teacher_key(
    year_text: str, group_text: str, name_text: str
) -> tuple[int, str, str] | None:
    year_text = year_text.strip()
    group_text = group_text.strip()
    name_text = name_text.strip()
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
    return year, group_text, name_text


def _handle_delete(year_text: str, group_text: str, name_text: str) -> bool:
    """선택한 행의 기본 키로만 삭제한다. 선택이 없으면 입력 칸의 세 키로 삭제한다."""
    edit_raw = st.session_state.get("teacher_edit_key")
    try:
        if edit_raw:
            # 그리드에서 고른 행의 키만 사용한다. 입력 칸을 바꿔도 다른 행이 지워지지 않는다.
            key = _as_teacher_key(edit_raw)
        else:
            parsed = _parse_teacher_key(year_text, group_text, name_text)
            if parsed is None:
                return False
            year, group, name = parsed
            key = _make_teacher_key(year, name, group)
        _delete_teacher(key)
    except Exception as exc:  # noqa: BLE001
        _alert(f"삭제하지 못했습니다: {exc}")
        return False

    st.session_state["teacher_clear_requested"] = True
    _refresh_teacher_list(key["year"])
    return True


def _apply_form_overrides() -> None:
    """선택 행을 위젯이 그려지기 전에 입력 칸에 반영한다."""
    if st.session_state.pop("teacher_clear_requested", False):
        _clear_form()
        return

    fill = st.session_state.pop("teacher_pending_fill", None)
    if not fill:
        return
    st.session_state["teacher_input_year"] = fill["year"]
    st.session_state["teacher_input_group"] = fill["group"]
    st.session_state["teacher_input_name"] = fill["name"]
    st.session_state["teacher_input_phone"] = fill["phone"]
    st.session_state["teacher_input_address"] = fill["address"]
    st.session_state["teacher_edit_key"] = _as_teacher_key(fill["key"])


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
        "key": _make_teacher_key(year, name, group),
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

    col_address, col_save, col_delete = st.columns(
        [4.2, 0.7, 0.7], vertical_alignment="bottom"
    )
    with col_address:
        address_text = st.text_input("주소", key="teacher_input_address")
    with col_save:
        submitted = st.button("저장", use_container_width=True, key="teacher_save_btn")
    with col_delete:
        deleted = st.button("삭제", use_container_width=True, key="teacher_delete_btn")

    if submitted:
        saved = _handle_save(year_text, group_text, name_text, phone_text, address_text)
        if saved is not None:
            st.session_state["teacher_saved_msg"] = True
            _refresh_teacher_list(saved)
            st.rerun()

    if deleted:
        if _handle_delete(year_text, group_text, name_text):
            st.session_state["teacher_deleted_msg"] = True
            st.rerun()

    if st.session_state.pop("teacher_saved_msg", False):
        st.success("저장했습니다.")
    if st.session_state.pop("teacher_deleted_msg", False):
        st.success("삭제했습니다.")

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
