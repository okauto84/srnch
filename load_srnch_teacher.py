"""담임 매칭 엑셀을 srnch_teacher에 적재한다.

엑셀 열: 학생이름, 어린이 조직 div, 반, 담임 선생님
- 학생이름 끝의 영문 한 글자는 srnch_members.name_distinct 이다.
- '1부1학년'과 반 1은 class_div '1-1-1' 이다.
- 연도 열이 없으므로 --year 를 쓴다. 기본값은 2026.
- member_id 는 이름과 구분이 같은 srnch_members.id 이다.
  같은 이름과 구분이 여러 명이면 children_group_div 가 class_div 와 같은 행을 고른다.

비밀값은 환경 변수 또는 .streamlit/secrets.toml 의 SUPABASE_PROJECT, SUPABASE_KEY 이다.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openpyxl import load_workbook
from supabase import Client, create_client

CLASS_DIV_RE = re.compile(r"^(\d+)부(\d+)학년$")
NAME_MARK_RE = re.compile(r"^(.+?)([A-Za-z])$")
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Assignment:
    source_row: int
    raw_name: str
    name: str
    name_distinct: str
    class_div: str
    teacher_name: str


def split_student_name(raw: str) -> tuple[str, str]:
    """김예준F → (김예준, F). 영문 구분이 없으면 구분값은 빈 문자열."""
    text = raw.strip()
    matched = NAME_MARK_RE.fullmatch(text)
    if matched and re.search(r"[가-힣]", matched.group(1)):
        return matched.group(1).strip(), matched.group(2).upper()
    return text, ""


def to_class_div(org: str, class_no: object) -> str:
    """1부1학년 + 1 → 1-1-1."""
    matched = CLASS_DIV_RE.fullmatch(str(org).strip())
    if not matched:
        raise ValueError(f"어린이 조직 div 형식이 아닙니다: {org}")
    number = int(class_no)
    if number < 1:
        raise ValueError(f"반 번호가 올바르지 않습니다: {class_no}")
    return f"{int(matched.group(1))}-{int(matched.group(2))}-{number}"


def read_assignments(path: Path) -> list[Assignment]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[workbook.sheetnames[0]]
        rows = sheet.iter_rows(values_only=True)
        header = next(rows, None)
        expected = ("학생이름", "어린이 조직 div", "반", "담임 선생님")
        if tuple(str(cell).strip() if cell is not None else "" for cell in (header or ()))[:4] != expected:
            raise ValueError(f"첫 행은 {expected} 이어야 합니다.")

        assignments: list[Assignment] = []
        for index, row in enumerate(rows, start=2):
            if row is None or all(cell is None or str(cell).strip() == "" for cell in row[:4]):
                continue
            raw_name, org, class_no, teacher = row[:4]
            name, mark = split_student_name(str(raw_name or ""))
            teacher_name = str(teacher or "").strip()
            if not name or not teacher_name:
                raise ValueError(f"{index}행에 학생 이름 또는 담임 이름이 없습니다.")
            assignments.append(
                Assignment(
                    source_row=index,
                    raw_name=str(raw_name).strip(),
                    name=name,
                    name_distinct=mark,
                    class_div=to_class_div(str(org or ""), class_no),
                    teacher_name=teacher_name,
                )
            )
        return assignments
    finally:
        workbook.close()


def _supabase_url(project: str) -> str:
    project = project.strip().rstrip("/")
    if project.startswith("http://") or project.startswith("https://"):
        return project
    return f"https://{project}.supabase.co"


def load_supabase_config() -> tuple[str, str]:
    load_dotenv(ROOT / ".env")
    project = os.getenv("SUPABASE_PROJECT", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    secrets_path = ROOT / ".streamlit" / "secrets.toml"
    if secrets_path.is_file():
        with secrets_path.open("rb") as handle:
            secrets = tomllib.load(handle)
        project = project or str(secrets.get("SUPABASE_PROJECT", "")).strip()
        key = key or str(secrets.get("SUPABASE_KEY", "")).strip()
    if not project or not key:
        raise RuntimeError(
            "SUPABASE_PROJECT, SUPABASE_KEY 가 환경 변수 또는 .streamlit/secrets.toml 에 필요합니다."
        )
    return project, key


def fetch_members(client: Client) -> list[dict]:
    rows: list[dict] = []
    start = 0
    page_size = 1000
    while True:
        response = (
            client.table("srnch_members")
            .select("id,name,name_distinct,children_group_div")
            .order("id")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        start += page_size


def _member_mark(member: dict) -> str:
    return str(member.get("name_distinct") or "").strip().upper()


def _member_name(member: dict) -> str:
    return str(member.get("name") or "").strip()


def match_assignments(
    assignments: list[Assignment], members: list[dict]
) -> tuple[list[tuple[Assignment, dict]], list[Assignment], list[tuple[Assignment, list[dict]]]]:
    by_name: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_label: dict[str, list[dict]] = defaultdict(list)
    for member in members:
        name = _member_name(member)
        mark = _member_mark(member)
        if not name or member.get("id") is None:
            continue
        by_name[(name, mark)].append(member)
        by_label[f"{name}{mark}"].append(member)

    matched: list[tuple[Assignment, dict]] = []
    unmatched: list[Assignment] = []
    ambiguous: list[tuple[Assignment, list[dict]]] = []

    for assignment in assignments:
        candidates = by_name.get((assignment.name, assignment.name_distinct), [])
        if not candidates:
            candidates = by_label.get(assignment.raw_name, [])
        if len(candidates) > 1:
            same_class = [
                member
                for member in candidates
                if str(member.get("children_group_div") or "").strip() == assignment.class_div
            ]
            if len(same_class) == 1:
                candidates = same_class
        if len(candidates) == 1:
            matched.append((assignment, candidates[0]))
        elif len(candidates) > 1:
            ambiguous.append((assignment, candidates))
        else:
            unmatched.append(assignment)
    return matched, unmatched, ambiguous


def build_rows(year: int, matched: list[tuple[Assignment, dict]]) -> list[dict]:
    return [
        {
            "year": year,
            "teacher_name": assignment.teacher_name,
            "class_div": assignment.class_div,
            "member_id": member["id"],
        }
        for assignment, member in matched
    ]


def upsert_teachers(client: Client, rows: list[dict]) -> int:
    batch_size = 100
    loaded = 0
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        client.table("srnch_teacher").upsert(chunk, on_conflict="year,member_id").execute()
        loaded += len(chunk)
    return loaded


def _print_problems(
    matched: list[tuple[Assignment, dict]],
    unmatched: list[Assignment],
    ambiguous: list[tuple[Assignment, list[dict]]],
) -> None:
    mismatches = [
        (assignment, member)
        for assignment, member in matched
        if str(member.get("children_group_div") or "").strip() != assignment.class_div
    ]
    print(f"매칭 {len(matched)}건, 없음 {len(unmatched)}건, 중복 {len(ambiguous)}건")
    print(f"회원 조직과 엑셀 반이 다른 배정 {len(mismatches)}건")
    for assignment in unmatched:
        print(
            f"  없음 {assignment.source_row}행 {assignment.raw_name} {assignment.class_div} {assignment.teacher_name}"
        )
    for assignment, candidates in ambiguous:
        ids = ", ".join(str(member.get("id")) for member in candidates)
        print(f"  중복 {assignment.source_row}행 {assignment.raw_name} 후보 id={ids}")
    for assignment, member in mismatches:
        print(
            "  조직다름 "
            f"{assignment.raw_name} 엑셀 {assignment.class_div} "
            f"회원 {member.get('children_group_div') or '-'} id={member.get('id')}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="담임 매칭 엑셀을 srnch_teacher에 적재합니다.")
    parser.add_argument("excel", nargs="?", default=r"d:\teacher.xlsx", help="매칭 엑셀 경로")
    parser.add_argument("--year", type=int, default=2026, help="배정 연도. 엑셀에는 연도가 없습니다.")
    parser.add_argument("--dry-run", action="store_true", help="적재하지 않고 매칭 결과만 출력합니다.")
    args = parser.parse_args(argv)

    if not 2000 <= args.year <= 2100:
        print("연도는 2000부터 2100 사이여야 합니다.", file=sys.stderr)
        return 1

    path = Path(args.excel)
    assignments = read_assignments(path)
    print(f"엑셀 {len(assignments)}건, 연도 {args.year}")

    project, key = load_supabase_config()
    client = create_client(_supabase_url(project), key)
    members = fetch_members(client)
    print(f"srnch_members {len(members)}건")

    matched, unmatched, ambiguous = match_assignments(assignments, members)
    _print_problems(matched, unmatched, ambiguous)
    rows = build_rows(args.year, matched)
    if args.dry_run:
        print(f"dry-run: 적재 대상 {len(rows)}건")
        return 0 if not unmatched and not ambiguous else 1
    if not rows:
        print("적재할 배정이 없습니다.", file=sys.stderr)
        return 1

    loaded = upsert_teachers(client, rows)
    print(f"srnch_teacher {args.year}년 {loaded}건 적재")
    return 0 if not unmatched and not ambiguous else 1


if __name__ == "__main__":
    raise SystemExit(main())
