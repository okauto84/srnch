"""관리 탭: 디모데(watching) 회원 목록 수집 후 Supabase srnch_members 적재."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests
import streamlit as st
import urllib3
from supabase import Client, create_client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MEMBER_FIELDS = (
    "id",
    "name",
    "name_distinct",
    "children_group",
    "part",
    "grade",
    "class",
    "member_type1",
    "member_type2",
    "birth_date",
    "age",
    "mobile",
    "gender",
    "spouse_duty",
    "household_head",
    "relationship_to_head",
    "jibeon_address",
    "duty1",
    "duty2",
    "family",
    "registered_at",
    "last_updated_at",
    "last_visit_at",
    "last_attendance_at",
    "last_offering_at",
    "welcome_at",
    "spouse_mobile",
    "leader1",
    "leader1_duty1",
    "leader1_duty2",
    "leader1_mobile",
    "leader1_children_group",
    "leader2",
    "leader2_duty1",
    "leader2_duty2",
    "leader2_mobile",
    "leader2_children_group",
    "created_at",
    "updated_at",
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


def _get_supabase() -> Client:
    return create_client(_supabase_url(_secret("SUPABASE_PROJECT")), _secret("SUPABASE_KEY"))


def _site_root(base_url: str) -> str:
    """base URL에서 site root 경로를 추출한다."""
    parsed = urlparse(base_url.strip())
    parts = [p for p in parsed.path.split("/") if p]
    site = parts[0] if parts else ""
    path = f"/{site}" if site else ""
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")


def _origin(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return None
    text = text.replace(".", "-").replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date().isoformat()
        except ValueError:
            continue
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").date().isoformat()
        except ValueError:
            return None
    return None


def _parse_timestamptz(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).isoformat()

    text = str(value).strip()
    if not text:
        return None
    text = text.replace(".", "-").replace("/", "-")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text[:26], fmt).isoformat()
        except ValueError:
            continue
    return _parse_date(text)


def _children_group_category(app_js: str) -> str:
    """appJs에서 '어린이' 조직 카테고리 코드(예: extended2)를 읽는다."""
    marker = "global.data.group.category = JSON.parse('"
    start = app_js.find(marker)
    if start >= 0:
        start += len(marker)
        end = app_js.find("');", start)
        raw = app_js[start:end] if end > start else ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        for item in data.get("list") or []:
            if item.get("title") == "어린이" and item.get("name"):
                return str(item["name"])
        own = (data.get("names") or {}).get("own") or []
        if own:
            return str(own[0])
    own_match = re.search(r'"own":\["([^"]+)"\]', app_js)
    if own_match:
        return own_match.group(1)
    return "extended2"


def split_children_group(value: str | None) -> tuple[int | None, int | None, int | None]:
    """어린이 조직 문구에서 부, 학년, 반을 읽는다.

    03. 유년-유년2부-2학년-11반 → part=2, grade=2, class=11
    03. 유년-유년1부-1학년-5반 → part=1, grade=1, class=5
    """
    if not value:
        return None, None, None
    dept = re.search(r"유년\s*(\d+)\s*부", value)
    grade = re.search(r"(\d+)\s*학년", value)
    klass = re.search(r"(\d+)\s*반", value)
    if not (dept and grade and klass):
        return None, None, None
    return int(dept.group(1)), int(grade.group(1)), int(klass.group(1))


def _first_text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        text = _as_text(row.get(key))
        if text:
            return text
    return None


def map_person_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """디모데 person/list 응답을 엑셀 컬럼 기준 srnch_members 레코드로 변환."""
    member_id = _as_int(row.get("id"))
    name = _as_text(row.get("name"))
    if member_id is None or not name:
        return None

    children_group = _first_text(row, "group", "group1", "group2", "mission", "mission1")
    part, grade, klass = split_children_group(children_group)
    jibeon_address = _first_text(row, "addrDongAddr", "addrRoadAddr")
    if not jibeon_address:
        parts = [
            _as_text(row.get("addrSido")) or "",
            _as_text(row.get("addrSigungu")) or "",
            _as_text(row.get("addrDong")) or "",
            _as_text(row.get("addrDetail")) or "",
        ]
        jibeon_address = " ".join(p for p in parts if p) or None

    return {
        "id": member_id,
        "name": name,
        "name_distinct": _as_text(row.get("nameDistinct")),
        "children_group": children_group,
        "part": part,
        "grade": grade,
        "class": klass,
        "member_type1": _first_text(row, "state1", "status"),
        "member_type2": _as_text(row.get("state2")),
        "birth_date": _parse_date(row.get("birthDate")),
        "age": _as_int(row.get("age")),
        "mobile": _as_text(row.get("mobileNum")),
        "gender": _as_text(row.get("gender")),
        "spouse_duty": _first_text(row, "partnerDuty1", "partnerdutyIid"),
        "household_head": _as_text(row.get("core")),
        "relationship_to_head": _as_text(row.get("coreRelative")),
        "jibeon_address": jibeon_address,
        "duty1": _as_text(row.get("duty1")),
        "duty2": _as_text(row.get("duty2")),
        "family": _as_text(row.get("family")),
        "registered_at": _parse_timestamptz(row.get("regDate")),
        "last_updated_at": _parse_timestamptz(row.get("updateDate")),
        "last_visit_at": _parse_date(row.get("lastVisitDate")),
        "last_attendance_at": _parse_date(row.get("lastAttDate")),
        "last_offering_at": _parse_date(row.get("lastOfferDate")),
        "welcome_at": _parse_date(row.get("welcomeDate")),
        "spouse_mobile": _as_text(row.get("partnerMobileNum")),
        "leader1": _as_text(row.get("leader1")),
        "leader1_duty1": _first_text(row, "leader1Duty1", "leader1Duty"),
        "leader1_duty2": _as_text(row.get("leader1Duty2")),
        "leader1_mobile": _first_text(row, "leader1MobileNum", "leader1Mobile"),
        "leader1_children_group": _first_text(row, "leader1Group", "leader1ChildrenGroup"),
        "leader2": _as_text(row.get("leader2")),
        "leader2_duty1": _first_text(row, "leader2Duty1", "leader2Duty"),
        "leader2_duty2": _as_text(row.get("leader2Duty2")),
        "leader2_mobile": _first_text(row, "leader2MobileNum", "leader2Mobile"),
        "leader2_children_group": _first_text(row, "leader2Group", "leader2ChildrenGroup"),
        "created_at": date.today().isoformat(),
        "updated_at": date.today().isoformat(),
    }


class DimodeClient:
    def __init__(self, base_url: str, login_id: str, password: str, members_url: str):
        self.base_url = base_url
        self.site_root = _site_root(base_url)
        self.origin = _origin(base_url)
        self.login_id = login_id
        self.password = password
        self.members_url = members_url
        self.signal = ""
        self.group_category = "extended2"
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Origin": self.origin,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }
        )

    def login(self) -> None:
        home = self.session.get(self.site_root, timeout=30)
        home.raise_for_status()

        response = self.session.post(
            f"{self.site_root}/api/account/login",
            data={
                "loginId": self.login_id,
                "loginPwd": self.password,
                "log": "true",
            },
            headers={"Signal": "", "Referer": self.site_root},
            timeout=30,
        )
        response.raise_for_status()
        result = response.text.strip().strip('"')
        if result != "success":
            raise RuntimeError(f"디모데 로그인 실패: {result}")

    def _load_signal(self) -> None:
        members_page = self.session.get(
            self.members_url.split("#")[0],
            headers={"Referer": self.site_root},
            timeout=30,
        )
        members_page.raise_for_status()

        year_match = re.search(r"[?&]year=(\d{4})", self.members_url)
        base_year = year_match.group(1) if year_match else "2026"

        app_js = self.session.get(
            f"{self.site_root}/load/appJs",
            params={
                "program": "member",
                "baseYear": base_year,
                "lang": "ko",
                "interface": "desktop",
                "windowType": "current",
            },
            headers={"Referer": self.members_url.split("#")[0]},
            timeout=60,
        )
        app_js.raise_for_status()

        match = re.search(r"global\.data\.signal\s*=\s*'([^']+)'", app_js.text)
        if not match:
            match = re.search(r'global\.data\.signal\s*=\s*"([^"]+)"', app_js.text)
        if not match:
            raise RuntimeError("appJs에서 Signal 값을 찾지 못했습니다.")
        self.signal = match.group(1)
        self.group_category = _children_group_category(app_js.text)

    def fetch_members(self) -> list[dict[str, Any]]:
        self._load_signal()

        year_match = re.search(r"[?&]year=(\d{4})", self.members_url)
        base_year = int(year_match.group(1)) if year_match else 2026

        members: list[dict[str, Any]] = []
        skip = 0
        take = 500
        total = None

        while True:
            response = self.session.post(
                f"{self.site_root}/api/person/list",
                data={
                    "baseYear": base_year,
                    "program": "member",
                    "log": "false",
                    "groupCategory": self.group_category,
                    "skip": skip,
                    "take": take,
                },
                headers={
                    "Signal": self.signal,
                    "Referer": self.members_url.split("#")[0],
                },
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("회원 목록 API 응답 형식이 올바르지 않습니다.")

            rows = payload.get("data") or []
            if not isinstance(rows, list):
                raise RuntimeError("회원 목록 data 배열을 찾지 못했습니다.")

            if total is None:
                total = int(payload.get("count") or 0)

            for row in rows:
                if isinstance(row, dict):
                    mapped = map_person_row(row)
                    if mapped:
                        members.append(mapped)

            skip += len(rows)
            if not rows or (total is not None and skip >= total) or len(rows) < take:
                break

        if not members:
            raise RuntimeError("수집된 회원 데이터가 없습니다.")
        return members


def upsert_members(client: Client, members: list[dict[str, Any]]) -> int:
    # 전체 동기화: 기존 데이터 삭제 후 재적재
    client.table("srnch_members").delete().gte("id", 0).execute()

    batch_size = 100
    inserted = 0
    for i in range(0, len(members), batch_size):
        chunk = [{k: row.get(k) for k in MEMBER_FIELDS} for row in members[i : i + batch_size]]
        client.table("srnch_members").upsert(chunk, on_conflict="id").execute()
        inserted += len(chunk)
    return inserted


def sync_members_from_dimode() -> tuple[int, list[dict[str, Any]]]:
    client_dimode = DimodeClient(
        base_url=_secret("W_DIMODE_URL"),
        login_id=_secret("W_DIMODE_ID"),
        password=_secret("W_DIMODE_PW"),
        members_url=_secret("W_DIMODE_URL_MEMBERS"),
    )
    client_dimode.login()
    members = client_dimode.fetch_members()
    count = upsert_members(_get_supabase(), members)
    return count, members[:20]


def _missing_secrets(names: tuple[str, ...]) -> list[str]:
    missing = []
    for key in names:
        try:
            _secret(key)
        except Exception:  # noqa: BLE001
            missing.append(key)
    return missing


def _run_batch2027() -> str:
    """이 파일과 같은 경로의 batch2027.py를 실행하고 출력 내용을 돌려준다."""
    script = Path(__file__).resolve().parent / "batch2027.py"
    if not script.is_file():
        raise FileNotFoundError(f"배치 스크립트가 없습니다: {script}")
    env = os.environ.copy()
    env["SUPABASE_PROJECT"] = _secret("SUPABASE_PROJECT")
    env["SUPABASE_KEY"] = _secret("SUPABASE_KEY")
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(script.parent),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail or f"종료 코드 {completed.returncode}")
    return completed.stdout.strip()


def render() -> None:
    st.subheader("관리")
    st.caption("디모데 회원 목록을 수집하여 Supabase `srnch_members`에 적재합니다.")

    missing_supabase = _missing_secrets(("SUPABASE_PROJECT", "SUPABASE_KEY"))
    missing_dimode = _missing_secrets(
        ("W_DIMODE_URL", "W_DIMODE_ID", "W_DIMODE_PW", "W_DIMODE_URL_MEMBERS")
    )
    if missing_supabase:
        st.error("다음 Streamlit secrets 변수가 필요합니다: " + ", ".join(missing_supabase))
        return

    sync_col, batch_col, _ = st.columns([1.3, 1.5, 3.2])
    with sync_col:
        sync_clicked = st.button("회원 동기화 실행", type="primary")
    with batch_col:
        batch_clicked = st.button("(임시)batch2027")

    if missing_dimode:
        st.caption("회원 동기화에는 다음 secrets가 필요합니다: " + ", ".join(missing_dimode))

    if sync_clicked:
        if missing_dimode:
            st.error("다음 Streamlit secrets 변수가 필요합니다: " + ", ".join(missing_dimode))
        else:
            with st.spinner("로그인 및 회원 수집 중..."):
                try:
                    count, preview = sync_members_from_dimode()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"동기화 실패: {exc}")
                    return
            st.success(f"srnch_members에 {count}건 적재 완료")
            if preview:
                st.dataframe(preview, use_container_width=True)

    if batch_clicked:
        with st.spinner("batch2027.py 실행 중..."):
            try:
                report = _run_batch2027()
            except Exception as exc:  # noqa: BLE001
                st.error(f"batch2027 실패: {exc}")
                return
        st.success("srnch_members에 year=2027 재배치 적재를 마쳤습니다.")
        st.text(report)
