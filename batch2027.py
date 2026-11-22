"""data 폴더의 2027 명단 엑셀을 최대 9반으로 재배치한 뒤 srnch_members에 넣는다.

조직 컬럼에서 부·학년·반을 읽고, 출석 수가 한 반에 몰리지 않도록
높은 출석부터 1반, 2반, … 순으로 한 명씩 나누어 배정한다.
엑셀 하나마다 부·학년을 따로 재배치한다.
같은 스크립트를 다시 실행하면 해당 연도·부·학년 행만 바꾼다.
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import openpyxl

YEAR = 2027
MAX_CLASSES = 9
TABLE = "srnch_members"
EXCEL_PATH = Path(__file__).resolve().parent / "data"

_PART_RE = re.compile(r"(?:유치|유년)\s*(\d+)\s*부")
_GRADE_RE = re.compile(r"(\d+)\s*학년")
_CLASS_RE = re.compile(r"(\d+)\s*반")


@dataclass
class Student:
    name: str
    name_distinct: str | None
    children_group: str
    part: int
    grade: int
    source_class: int
    attendance: int
    order: int
    new_class: int = 0


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _attendance(value: object) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        raise ValueError(f"출석 값을 숫자로 읽을 수 없습니다: {value!r}")
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    return int(float(text))


def parse_org(value: str) -> tuple[int, int, int]:
    """조직 문구에서 부, 학년, 반을 읽는다.

    04.유치 유치1부 믿음 01반 → part=1, grade=1, class=1
    학년 숫자가 없고 '믿음'이면 1학년으로 본다.
    """
    part_match = _PART_RE.search(value)
    class_match = _CLASS_RE.search(value)
    if not part_match or not class_match:
        raise ValueError(f"조직에서 부 또는 반을 찾지 못했습니다: {value}")
    grade_match = _GRADE_RE.search(value)
    if grade_match:
        grade = int(grade_match.group(1))
    elif "믿음" in value:
        grade = 1
    else:
        raise ValueError(f"조직에서 학년을 찾지 못했습니다: {value}")
    return int(part_match.group(1)), grade, int(class_match.group(1))


def rewrite_class(children_group: str, klass: int) -> str:
    """조직 문구의 반 번호만 새 반으로 바꾼다."""
    match = _CLASS_RE.search(children_group)
    if not match:
        raise ValueError(f"조직에서 반을 찾지 못했습니다: {children_group}")
    width = len(match.group(1))
    replaced = f"{klass:0{width}d}반"
    return children_group[: match.start()] + replaced + children_group[match.end() :]


def load_students(path: Path) -> list[Student]:
    workbook = openpyxl.load_workbook(path, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError(f"시트가 비어 있습니다: {path}")

    header = [_cell_text(cell) for cell in rows[0]]
    try:
        name_at = header.index("대상자")
        distinct_at = header.index("구분자")
        org_at = header.index("조직")
        attend_at = header.index("출석")
    except ValueError as exc:
        raise ValueError(f"필요한 컬럼이 없습니다. 헤더: {header}") from exc

    students: list[Student] = []
    for offset, row in enumerate(rows[1:], start=2):
        name = _cell_text(row[name_at] if name_at < len(row) else None)
        if not name:
            continue
        org = _cell_text(row[org_at] if org_at < len(row) else None)
        part, grade, source_class = parse_org(org)
        distinct = _cell_text(row[distinct_at] if distinct_at < len(row) else None)
        try:
            attendance = _attendance(row[attend_at] if attend_at < len(row) else None)
        except ValueError as exc:
            raise ValueError(f"{offset}행 {name} 출석 오류: {exc}") from exc
        students.append(
            Student(
                name=name,
                name_distinct=distinct or None,
                children_group=org,
                part=part,
                grade=grade,
                source_class=source_class,
                attendance=attendance,
                order=offset,
            )
        )
    if not students:
        raise ValueError(f"학생이 없습니다: {path}")
    return students


def assign_classes(students: list[Student], max_classes: int = MAX_CLASSES) -> int:
    """출석이 높은 학생부터 1반에서 마지막 반으로 한 명씩 돌며 배정한다.

    같은 출석 수는 반마다 최대 1명 차이로 나뉘고, 각 반은 높은 출석과 낮은 출석을
    함께 받는다. 반 인원도 최대 1명 차이 난다.
    반환값은 실제로 만든 반 수(최대 max_classes)이다.
    """
    if max_classes < 1:
        raise ValueError("반 수는 1 이상이어야 합니다.")
    class_count = min(max_classes, len(students))
    ordered = sorted(students, key=lambda student: (-student.attendance, student.order))
    for turn, student in enumerate(ordered):
        student.new_class = (turn % class_count) + 1
    return class_count


def _cohort(students: list[Student]) -> tuple[int, int]:
    parts = {(student.part, student.grade) for student in students}
    if len(parts) != 1:
        listed = ", ".join(f"{part}부 {grade}학년" for part, grade in sorted(parts))
        raise ValueError(f"한 파일에 부·학년이 여러 개입니다: {listed}")
    return parts.pop()


def build_rows(students: list[Student], start_id: int) -> list[dict]:
    today = date.today().isoformat()
    ordered = sorted(students, key=lambda student: (student.new_class, student.order))
    rows: list[dict] = []
    for offset, student in enumerate(ordered, start=1):
        rows.append(
            {
                "id": start_id + offset,
                "year": YEAR,
                "name": student.name,
                "name_distinct": student.name_distinct,
                "children_group": rewrite_class(student.children_group, student.new_class),
                "part": student.part,
                "grade": student.grade,
                "class": student.new_class,
                "created_at": today,
                "updated_at": today,
            }
        )
    return rows


def summarize(students: list[Student], class_count: int) -> str:
    lines = [
        f"{students[0].part}부 {students[0].grade}학년 {len(students)}명 → {class_count}반",
    ]
    for klass in range(1, class_count + 1):
        group = [student for student in students if student.new_class == klass]
        counts = Counter(student.attendance for student in group)
        attendance = " ".join(
            f"{score}×{counts[score]}" for score in sorted(counts, reverse=True)
        )
        names = ", ".join(
            student.name + (student.name_distinct or "")
            for student in sorted(group, key=lambda student: student.order)
        )
        lines.append(f"{klass:02d}반 {len(group)}명 [{attendance}] {names}")
    return "\n".join(lines)


def _secret_tables() -> list[dict]:
    try:
        import tomllib
    except ModuleNotFoundError:
        return []
    paths = [
        Path(__file__).resolve().parent / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ]
    loaded: list[dict] = []
    for path in paths:
        if not path.is_file():
            continue
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        if isinstance(data, dict):
            loaded.append(data)
    return loaded


def _setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    for table in _secret_tables():
        raw = table.get(name)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return ""


def _supabase_url(project: str) -> str:
    project = project.strip().rstrip("/")
    if project.startswith("http://") or project.startswith("https://"):
        return project
    return f"https://{project}.supabase.co"


def supabase_client():
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        pass
    else:
        load_dotenv(Path(__file__).resolve().parent / ".env")
    from supabase import create_client

    project = _setting("SUPABASE_PROJECT") or _setting("SUPABASE_URL")
    key = _setting("SUPABASE_KEY")
    if not project or not key:
        raise RuntimeError(
            "SUPABASE_PROJECT(또는 SUPABASE_URL)와 SUPABASE_KEY가 필요합니다. "
            "환경 변수, .env, .streamlit/secrets.toml 중 한 곳에 두세요."
        )
    return create_client(_supabase_url(project), key)


def _next_id(client) -> int:
    response = (
        client.table(TABLE).select("id").order("id", desc=True).limit(1).execute()
    )
    rows = response.data or []
    if not rows or rows[0].get("id") is None:
        return 0
    return int(rows[0]["id"])


def _existing_ids(client, part: int, grade: int) -> list[int]:
    found: list[int] = []
    start = 0
    page = 1000
    while True:
        response = (
            client.table(TABLE)
            .select("id")
            .eq("year", YEAR)
            .eq("part", part)
            .eq("grade", grade)
            .range(start, start + page - 1)
            .execute()
        )
        batch = response.data or []
        found.extend(int(row["id"]) for row in batch if row.get("id") is not None)
        if len(batch) < page:
            return found
        start += page


def _delete_ids(client, ids: list[int]) -> None:
    for start in range(0, len(ids), 100):
        chunk = ids[start : start + 100]
        client.table(TABLE).delete().in_("id", chunk).eq("year", YEAR).execute()


def excel_files(path: Path) -> list[Path]:
    """파일 하나 또는 폴더 안의 xlsx 전체를 이름순으로 돌려준다."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"명단 경로가 없습니다: {path}")
    found = sorted(
        item
        for item in path.iterdir()
        if item.is_file() and item.suffix.lower() == ".xlsx" and not item.name.startswith("~$")
    )
    if not found:
        raise FileNotFoundError(f"엑셀 파일이 없습니다: {path}")
    return found


def _insert_rows(client, rows: list[dict]) -> None:
    for start in range(0, len(rows), 100):
        client.table(TABLE).insert(rows[start : start + 100]).execute()


def _replace_cohort(client, students: list[Student], start_id: int) -> int:
    """새 반 배정을 넣은 뒤, 같은 연도·부·학년의 이전 행을 지운다."""
    previous_ids = _existing_ids(client, students[0].part, students[0].grade)
    rows = build_rows(students, start_id)
    _insert_rows(client, rows)
    new_ids = {row["id"] for row in rows}
    stale = [member_id for member_id in previous_ids if member_id not in new_ids]
    if stale:
        _delete_ids(client, stale)
    return int(rows[-1]["id"])


def run_batch(source: Path | None = None, *, dry_run: bool = False, client=None) -> str:
    """data 폴더의 엑셀마다 반을 재배치하고, 요청하면 srnch_members에 넣는다."""
    paths = excel_files(EXCEL_PATH if source is None else source)
    blocks: list[str] = []
    prepared: list[list[Student]] = []
    seen: set[tuple[int, int]] = set()
    for path in paths:
        students = load_students(path)
        part, grade = _cohort(students)
        if (part, grade) in seen:
            raise ValueError(f"{part}부 {grade}학년이 엑셀 두 곳에 있습니다: {path.name}")
        seen.add((part, grade))
        class_count = assign_classes(students, MAX_CLASSES)
        blocks.append(f"[{path.name}]\n{summarize(students, class_count)}")
        prepared.append(students)

    if dry_run:
        blocks.append("dry-run: insert 하지 않았습니다.")
        return "\n\n".join(blocks)

    db = supabase_client() if client is None else client
    last_id = _next_id(db)
    total = 0
    for students in prepared:
        last_id = _replace_cohort(db, students, last_id)
        total += len(students)
    blocks.append(f"srnch_members에 year={YEAR} {total}명을 넣었습니다.")
    return "\n\n".join(blocks)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="data 폴더의 2027 명단을 재배치해 srnch_members에 넣습니다."
    )
    parser.add_argument(
        "--excel",
        type=Path,
        default=EXCEL_PATH,
        help="명단 폴더 또는 xlsx 파일. 폴더이면 그 안의 xlsx를 모두 처리합니다.",
    )
    parser.add_argument("--dry-run", action="store_true", help="배정 결과만 출력하고 insert 하지 않습니다.")
    args = parser.parse_args()
    print(run_batch(args.excel, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
