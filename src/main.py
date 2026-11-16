"""Entry point for authenticated data collection."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()

    base_url = os.getenv("SITE_BASE_URL", "").strip()
    username = os.getenv("SITE_USERNAME", "").strip()
    password = os.getenv("SITE_PASSWORD", "").strip()

    if not base_url or not username or not password:
        print(
            "SITE_BASE_URL, SITE_USERNAME, SITE_PASSWORD 를 .env 에 설정하세요.",
            file=sys.stderr,
        )
        return 1

    print("환경 변수 확인 완료. 대상 사이트/수집 규칙을 정한 뒤 수집 로직을 추가하세요.")
    print(f"base_url={base_url}")
    print(f"username={username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
