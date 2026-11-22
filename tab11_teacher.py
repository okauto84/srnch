"""담임정보 탭: 담임 정보를 srnch_teacher에 저장·조회한다."""

from __future__ import annotations

import re
from datetime import date

import streamlit as st
from supabase import create_client

_LEGACY_GROUP_RE = re.compile(r"^(\d+)-(\d+)-(\d+)$")
YEAR_OPTIONS = (2026, 2027)
GRID_COLUMNS = (
    ("year", "연도"),
    ("part", "부"),
    ("grade", "학년"),
    ("class", "반"),
    ("teacher_name", "이름"),
    ("phone", "연락처"),
    ("address", "주소"),
)
COLUMN_WIDTHS = {
    "연도": 80,
    "부": 56,
    "학년": 56,
    "반": 56,
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


# srnch_teacher 기본 키. 이 값이 모두 맞을 때만 한 행을 고치거나 지운다.
TEACHER_KEY_FIELDS = ("year", "teacher_name", "part", "grade", "class")
TEACHER_KEY_SELECT = "year,teacher_name,part,grade,class"


def _client():
    return create_client(_supabase_url(_secret("SUPABASE_PROJECT")), _secret("SUPABASE_KEY"))


def _parse_positive_int(value: object) -> int | None:
    """1 이상의 정수만 받는다. 01은 1로 본다."""
    text = str(value if value is not None else "").strip()
    if not text.isdigit():
        return None
    number = int(text)
    if number < 1:
        return None
    return number


def _make_teacher_key(
    year: int,
    teacher_name: str,
    part: object,
    grade: object,
    klass: object,
) -> dict:
    """기본 키를 정규화한다. 하나라도 비면 거부한다."""
    name = str(teacher_name).strip()
    if not isinstance(year, int):
        year = int(year)
    part_n = _parse_positive_int(part)
    grade_n = _parse_positive_int(grade)
    class_n = _parse_positive_int(klass)
    if not name or part_n is None or grade_n is None or class_n is None:
        raise ValueError("담임 키(year, teacher_name, part, grade, class)가 완전하지 않습니다.")
    return {
        "year": year,
        "teacher_name": name,
        "part": part_n,
        "grade": grade_n,
        "class": class_n,
    }


def _as_teacher_key(raw: dict | None) -> dict:
    """세션/선택 값에서 기본 키만 뽑아 검증한다."""
    if not raw:
        raise ValueError("담임 키가 없습니다.")
    source = dict(raw)
    if any(source.get(field) in (None, "") for field in ("part", "grade", "class")):
        match = _LEGACY_GROUP_RE.fullmatch(str(source.get("children_group_div") or "").strip())
        if match:
            source["part"], source["grade"], source["class"] = (
                int(part) for part in match.groups()
            )
    missing = [field for field in TEACHER_KEY_FIELDS if source.get(field) in (None, "")]
    if missing:
        raise ValueError(
            "담임 키가 완전하지 않습니다: " + ", ".join(missing)
        )
    return _make_teacher_key(
        int(source["year"]),
        str(source["teacher_name"]),
        source["part"],
        source["grade"],
        source["class"],
    )


def _filter_by_teacher_key(query, key: dict):
    """세 키 조건이 모두 있을 때만 필터한다. 다른 행이 걸리지 않게 한다."""
    key = _as_teacher_key(key)
    return (
        query.eq("year", key["year"])
        .eq("teacher_name", key["teacher_name"])
        .eq("part", key["part"])
        .eq("grade", key["grade"])
        .eq("class", key["class"])
    )


def _require_one_row(rows: list | None, action: str) -> dict:
    if not rows:
        raise LookupError(f"{action}할 담임 정보를 찾지 못했습니다.")
    if len(rows) != 1:
        raise RuntimeError(
            f"{action} 대상이 {len(rows)}건입니다. "
            "year, teacher_name, part, grade, class 키가 한 행만 가리켜야 합니다."
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
    part: object,
    grade: object,
    klass: object,
    teacher_name: str,
    phone: str,
    address: str,
) -> dict:
    key = _make_teacher_key(year, teacher_name, part, grade, klass)
    return {
        **key,
        "phone": phone or None,
        "address": address or None,
    }


def _save_teacher(
    year: int,
    part: object,
    grade: object,
    klass: object,
    teacher_name: str,
    phone: str,
    address: str,
) -> None:
    """연도, 부, 학년, 반, 이름, 연락처, 주소를 srnch_teacher에 새로 저장한다."""
    today = _today()
    payload = _teacher_payload(year, part, grade, klass, teacher_name, phone, address)
    payload["created_at"] = today
    payload["updated_at"] = today
    _client().table("srnch_teacher").insert(payload).execute()


def _update_teacher(
    edit_key: dict,
    year: int,
    part: object,
    grade: object,
    klass: object,
    teacher_name: str,
    phone: str,
    address: str,
) -> None:
    """선택한 행만, 기본 키 조건으로 고친다."""
    old_key = _as_teacher_key(edit_key)
    new_key = _make_teacher_key(year, teacher_name, part, grade, klass)
    if old_key == new_key:
        # 키가 같으면 연락처·주소만 바꿔 다른 행 키를 건드리지 않는다.
        payload = {
            "phone": phone or None,
            "address": address or None,
            "updated_at": _today(),
        }
    else:
        payload = _teacher_payload(year, part, grade, klass, teacher_name, phone, address)
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
        .select("year,part,grade,class,teacher_name,phone,address")
        .eq("year", year)
        .order("part")
        .order("grade")
        .order("class")
        .order("teacher_name")
        .execute()
    )
    return response.data or []


def _copy_teachers_to_next_year(source_year: int) -> tuple[int, int, int]:
    """선택 연도 담임 전체를 내년(year+1)으로 복사한다.

    Returns:
        (복사 건수, 이미 있어 건너뛴 건수, 대상 연도)
    """
    target_year = int(source_year) + 1
    client = _client()
    source_rows = (
        client.table("srnch_teacher")
        .select("part,grade,class,teacher_name,phone,address")
        .eq("year", source_year)
        .execute()
    ).data or []
    if not source_rows:
        raise LookupError(f"{source_year}년 담임 정보가 없습니다.")

    existing_rows = (
        client.table("srnch_teacher")
        .select("teacher_name,part,grade,class")
        .eq("year", target_year)
        .execute()
    ).data or []
    existing_keys = {
        (
            str(row.get("teacher_name") or ""),
            _parse_positive_int(row.get("part")),
            _parse_positive_int(row.get("grade")),
            _parse_positive_int(row.get("class")),
        )
        for row in existing_rows
    }

    today = _today()
    payloads: list[dict] = []
    skipped = 0
    for row in source_rows:
        name = str(row.get("teacher_name") or "").strip()
        part = _parse_positive_int(row.get("part"))
        grade = _parse_positive_int(row.get("grade"))
        klass = _parse_positive_int(row.get("class"))
        if not name or part is None or grade is None or klass is None:
            skipped += 1
            continue
        if (name, part, grade, klass) in existing_keys:
            skipped += 1
            continue
        payloads.append(
            {
                "year": target_year,
                "teacher_name": name,
                "part": part,
                "grade": grade,
                "class": klass,
                "phone": row.get("phone"),
                "address": row.get("address"),
                "created_at": today,
                "updated_at": today,
            }
        )

    if payloads:
        client.table("srnch_teacher").insert(payloads).execute()
    return len(payloads), skipped, target_year


def _handle_copy_next_year(source_year: int) -> bool:
    """내년도 복사 후 목록을 새로고침한다."""
    try:
        copied, skipped, target_year = _copy_teachers_to_next_year(int(source_year))
    except Exception as exc:  # noqa: BLE001
        _alert(f"내년도 복사에 실패했습니다: {exc}")
        return False

    if copied == 0 and skipped == 0:
        _alert(f"{source_year}년 담임 정보가 없습니다.")
        return False

    st.session_state["teacher_copied_msg"] = {
        "source_year": int(source_year),
        "target_year": target_year,
        "copied": copied,
        "skipped": skipped,
    }
    _refresh_teacher_list(target_year)
    return True


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
        str(key["part"]),
        str(key["grade"]),
        str(key["class"]),
        key["teacher_name"],
    )


def _handle_save(
    year_text: str,
    part_text: str,
    grade_text: str,
    class_text: str,
    name_text: str,
    phone_text: str,
    address_text: str,
) -> int | None:
    phone_text = phone_text.strip()
    address_text = address_text.strip()
    parsed = _parse_teacher_key(year_text, part_text, grade_text, class_text, name_text)
    if parsed is None:
        return None
    year, part, grade, klass, name_text = parsed
    new_key = _make_teacher_key(year, name_text, part, grade, klass)

    edit_raw = st.session_state.get("teacher_edit_key")
    try:
        edit_key = _as_teacher_key(edit_raw) if edit_raw else None
        # 선택한 행과 키가 같을 때만 수정한다.
        # 키가 다르면 신규 추가다. 예전처럼 이전 행 키를 바꿔 쓰면
        # 강미옥 행이 김지영으로 바뀌며 사라지는 일이 난다.
        if edit_key and _same_teacher(edit_key, new_key):
            _update_teacher(
                edit_key,
                new_key["year"],
                new_key["part"],
                new_key["grade"],
                new_key["class"],
                new_key["teacher_name"],
                phone_text,
                address_text,
            )
        else:
            if _teacher_exists(new_key):
                _alert(
                    "이미 같은 데이터가 있습니다: "
                    f"{new_key['year']} / {new_key['part']}부 {new_key['grade']}학년 {new_key['class']}반 / {new_key['teacher_name']}"
                )
                return None
            _save_teacher(
                new_key["year"],
                new_key["part"],
                new_key["grade"],
                new_key["class"],
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
    "teacher_input_part",
    "teacher_input_grade",
    "teacher_input_class",
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


def _list_year_options() -> list[int]:
    """기본 연도 + 내년도 복사로 생긴 연도를 선택지에 포함한다."""
    options = list(YEAR_OPTIONS)
    extra = st.session_state.get("teacher_extra_years") or []
    for year in extra:
        try:
            value = int(year)
        except (TypeError, ValueError):
            continue
        if value not in options:
            options.append(value)
    options.sort()
    return options


def _refresh_teacher_list(year: int | None = None) -> None:
    """저장·삭제 뒤 캐시를 비우고 그리드가 최신 목록을 다시 읽게 한다."""
    _fetch_teachers.clear()
    st.session_state["teacher_data_version"] = int(st.session_state.get("teacher_data_version", 0)) + 1
    st.session_state["teacher_grid_generation"] = (
        int(st.session_state.get("teacher_grid_generation", 0)) + 1
    )
    if year is None:
        return
    year = int(year)
    options = _list_year_options()
    if year not in options:
        extra = list(st.session_state.get("teacher_extra_years") or [])
        if year not in extra:
            extra.append(year)
            st.session_state["teacher_extra_years"] = extra
        options = _list_year_options()
    if year in options:
        st.session_state["teacher_list_year"] = year


def _parse_teacher_key(
    year_text: str,
    part_text: str,
    grade_text: str,
    class_text: str,
    name_text: str,
) -> tuple[int, int, int, int, str] | None:
    year_text = year_text.strip()
    part_text = part_text.strip()
    grade_text = grade_text.strip()
    class_text = class_text.strip()
    name_text = name_text.strip()
    missing = [
        label
        for label, value in (
            ("연도", year_text),
            ("부", part_text),
            ("학년", grade_text),
            ("반", class_text),
            ("이름", name_text),
        )
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
    part = _parse_positive_int(part_text)
    grade = _parse_positive_int(grade_text)
    klass = _parse_positive_int(class_text)
    if part is None or grade is None or klass is None:
        _alert("부, 학년, 반은 1 이상의 숫자로 입력하세요.")
        return None
    return year, part, grade, klass, name_text


def _handle_delete(
    year_text: str,
    part_text: str,
    grade_text: str,
    class_text: str,
    name_text: str,
) -> bool:
    """선택한 행의 기본 키로만 삭제한다. 선택이 없으면 입력 칸의 세 키로 삭제한다."""
    edit_raw = st.session_state.get("teacher_edit_key")
    try:
        if edit_raw:
            # 그리드에서 고른 행의 키만 사용한다. 입력 칸을 바꿔도 다른 행이 지워지지 않는다.
            key = _as_teacher_key(edit_raw)
        else:
            parsed = _parse_teacher_key(year_text, part_text, grade_text, class_text, name_text)
            if parsed is None:
                return False
            year, part, grade, klass, name = parsed
            key = _make_teacher_key(year, name, part, grade, klass)
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
    st.session_state["teacher_input_part"] = fill["part"]
    st.session_state["teacher_input_grade"] = fill["grade"]
    st.session_state["teacher_input_class"] = fill["class"]
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
    part = row.get("part")
    grade = row.get("grade")
    klass = row.get("class")
    name = str(row.get("teacher_name") or "")
    sig = (str(year), str(part), str(grade), str(klass), name)
    if sig == st.session_state.get("teacher_loaded_sig"):
        return
    try:
        key = _make_teacher_key(year, name, part, grade, klass)
    except ValueError:
        return
    st.session_state["teacher_loaded_sig"] = sig
    st.session_state["teacher_pending_fill"] = {
        "year": str(year),
        "part": str(key["part"]),
        "grade": str(key["grade"]),
        "class": str(key["class"]),
        "name": name,
        "phone": "" if row.get("phone") is None else str(row.get("phone")),
        "address": "" if row.get("address") is None else str(row.get("address")),
        "key": key,
    }
    st.rerun()


def render() -> None:
    """담임 정보 입력과 연도별 목록."""
    _apply_form_overrides()
    st.markdown("**담임 정보**")
    col_year, col_part, col_grade, col_class, col_name, col_phone = st.columns(
        [1, 0.7, 0.7, 0.7, 1.2, 1.6], vertical_alignment="bottom"
    )
    with col_year:
        year_text = st.text_input("연도", key="teacher_input_year")
    with col_part:
        part_text = st.text_input("부", placeholder="2", key="teacher_input_part")
    with col_grade:
        grade_text = st.text_input("학년", placeholder="2", key="teacher_input_grade")
    with col_class:
        class_text = st.text_input("반", placeholder="11", key="teacher_input_class")
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
        saved = _handle_save(
            year_text, part_text, grade_text, class_text, name_text, phone_text, address_text
        )
        if saved is not None:
            st.session_state["teacher_saved_msg"] = True
            _refresh_teacher_list(saved)
            st.rerun()

    if deleted:
        if _handle_delete(year_text, part_text, grade_text, class_text, name_text):
            st.session_state["teacher_deleted_msg"] = True
            st.rerun()

    if st.session_state.pop("teacher_saved_msg", False):
        st.success("저장했습니다.")
    if st.session_state.pop("teacher_deleted_msg", False):
        st.success("삭제했습니다.")
    copied_msg = st.session_state.pop("teacher_copied_msg", None)
    if copied_msg:
        copied = int(copied_msg["copied"])
        skipped = int(copied_msg["skipped"])
        source_year = int(copied_msg["source_year"])
        target_year = int(copied_msg["target_year"])
        if copied > 0:
            msg = f"{source_year}년 → {target_year}년으로 {copied}건 복사했습니다."
            if skipped:
                msg += f" (이미 있어 건너뜀 {skipped}건)"
            st.success(msg)
        else:
            st.info(
                f"{target_year}년에 이미 같은 담임이 있어 새로 복사한 건이 없습니다."
                f" (건너뜀 {skipped}건)"
            )

    version = int(st.session_state.get("teacher_data_version", 0))
    year_options = _list_year_options()
    if st.session_state.get("teacher_list_year") not in year_options:
        st.session_state["teacher_list_year"] = year_options[0]

    year_col, copy_col, _ = st.columns([1, 1.2, 3.8], vertical_alignment="bottom")
    with year_col:
        selected_year = st.selectbox(
            "연도",
            options=year_options,
            key="teacher_list_year",
        )
    with copy_col:
        copy_clicked = st.button(
            "내년도 복사",
            use_container_width=True,
            key="teacher_copy_next_year_btn",
        )

    if copy_clicked:
        if _handle_copy_next_year(int(selected_year)):
            st.rerun()

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
