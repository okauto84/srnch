"""관리 탭: 디모데(watching) 회원 목록 수집 후 Supabase srnch_members 적재."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests
import streamlit as st
import urllib3
from supabase import Client, create_client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MEMBER_FIELDS = (
    "name",
    "gender",
    "organization",
    "birth_date",
    "mobile",
    "household_head",
    "relationship_to_head",
    "address",
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
    """https://w.dimode.co.kr/srnch/... -> https://w.dimode.co.kr/srnch"""
    parsed = urlparse(base_url.strip())
    parts = [p for p in parsed.path.split("/") if p]
    site = parts[0] if parts else ""
    path = f"/{site}" if site else ""
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")


def _origin(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def _parse_birth_date(value: Any) -> str | None:
    if value is None:
        return None
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
    if len(digits) == 8:
        try:
            return datetime.strptime(digits, "%Y%m%d").date().isoformat()
        except ValueError:
            return None
    return None


def _compose_address(row: dict[str, Any]) -> str | None:
    for key in ("addrRoadAddr", "addrDongAddr"):
        val = row.get(key)
        if val:
            detail = str(row.get("addrDetail") or "").strip()
            base = str(val).strip()
            return f"{base} {detail}".strip() if detail else base

    parts = [
        str(row.get("addrSido") or "").strip(),
        str(row.get("addrSigungu") or "").strip(),
        str(row.get("addrDong") or "").strip(),
        str(row.get("addrRoad") or "").strip(),
        str(row.get("addrDetail") or "").strip(),
    ]
    joined = " ".join(p for p in parts if p)
    return joined or None


def _organization(row: dict[str, Any]) -> str | None:
    for key in ("group", "group1", "group2", "mission", "mission1"):
        val = row.get(key)
        if val:
            return str(val).strip()
    return None


def map_person_row(row: dict[str, Any]) -> dict[str, Any] | None:
    name = str(row.get("name") or "").strip()
    if not name:
        return None
    return {
        "name": name,
        "gender": (str(row.get("gender")).strip() if row.get("gender") else None),
        "organization": _organization(row),
        "birth_date": _parse_birth_date(row.get("birthDate")),
        "mobile": (str(row.get("mobileNum")).strip() if row.get("mobileNum") else None),
        "household_head": (str(row.get("core")).strip() if row.get("core") else None),
        "relationship_to_head": (
            str(row.get("coreRelative")).strip() if row.get("coreRelative") else None
        ),
        "address": _compose_address(row),
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

        # year 파라미터에서 baseYear 추출, 없으면 현재 URL 쿼리/기본값
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
                    "groupCategory": "",
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
    client.table("srnch_members").delete().neq("name", "").execute()
    batch_size = 200
    inserted = 0
    for i in range(0, len(members), batch_size):
        chunk = members[i : i + batch_size]
        client.table("srnch_members").insert(chunk).execute()
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


def render() -> None:
    st.subheader("관리")
    st.caption("디모데 회원 목록을 수집하여 Supabase `srnch_members`에 적재합니다.")

    required = [
        "SUPABASE_PROJECT",
        "SUPABASE_KEY",
        "W_DIMODE_URL",
        "W_DIMODE_ID",
        "W_DIMODE_PW",
        "W_DIMODE_URL_MEMBERS",
    ]
    missing = []
    for key in required:
        try:
            _secret(key)
        except Exception:  # noqa: BLE001
            missing.append(key)

    if missing:
        st.error("다음 secrets 변수가 필요합니다: " + ", ".join(missing))
        st.code(
            "\n".join(
                [
                    'SUPABASE_PROJECT = "your-project-ref"',
                    'SUPABASE_KEY = "your-service-role-key"',
                    'W_DIMODE_URL = "https://w.dimode.co.kr/srnch"',
                    'W_DIMODE_ID = "your-id"',
                    'W_DIMODE_PW = "your-password"',
                    'W_DIMODE_URL_MEMBERS = "https://w.dimode.co.kr/srnch/member/?year=2026&lang=ko#/person/list"',
                ]
            ),
            language="toml",
        )
        return

    host = urlparse(_secret("W_DIMODE_URL")).netloc or _secret("W_DIMODE_URL")
    st.write(f"대상: `{host}` / site=`{_site_root(_secret('W_DIMODE_URL'))}`")

    if st.button("회원 동기화 실행", type="primary"):
        with st.spinner("로그인 및 회원 수집 중..."):
            try:
                count, preview = sync_members_from_dimode()
            except Exception as exc:  # noqa: BLE001
                st.error(f"동기화 실패: {exc}")
                return

        st.success(f"srnch_members에 {count}건 적재 완료")
        if preview:
            st.dataframe(preview, use_container_width=True)
