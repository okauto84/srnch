"""통계 탭: 담임 정보를 srnch_teacher에 저장한다."""

from __future__ import annotations

import re

import streamlit as st
from supabase import create_client

GROUP_DIV_RE = re.compile(r"^[0-9]+-[0-9]+-[0-9]+$")


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


def _save_teacher(year: int, children_group_div: str, teacher_name: str) -> None:
    """연도, 조직, 이름을 srnch_teacher에 저장한다."""
    client = create_client(_supabase_url(_secret("SUPABASE_PROJECT")), _secret("SUPABASE_KEY"))
    (
        client.table("srnch_teacher")
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


def render() -> None:
    """담임 입력 카드."""
    card, _rest = st.columns([1, 2])
    with card:
        with st.container(border=True):
            st.markdown("**담임 정보**")
            with st.form("teacher_form", clear_on_submit=False):
                year_text = st.text_input("연도")
                group_text = st.text_input("조직", placeholder="1-1-5")
                name_text = st.text_input("이름")
                submitted = st.form_submit_button("저장")

            if not submitted:
                return

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
                return

            try:
                year = int(year_text)
            except ValueError:
                st.error("연도는 숫자로 입력하세요.")
                return
            if not 2000 <= year <= 2100:
                st.error("연도는 2000년부터 2100년까지 입력하세요.")
                return
            if not GROUP_DIV_RE.fullmatch(group_text):
                st.error("조직은 1-1-5 형식으로 입력하세요.")
                return

            try:
                _save_teacher(year, group_text, name_text)
            except Exception as exc:  # noqa: BLE001
                st.error(f"저장하지 못했습니다: {exc}")
                return
            st.success("저장했습니다.")
