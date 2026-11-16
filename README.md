# srnch

정상 로그인 계정으로 사이트 데이터를 수집하는 프로젝트입니다.

## 시작하기

1. Python 3.11+ 권장
2. 가상환경 생성 및 의존성 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

3. 환경 변수 설정

```bash
copy .env.example .env
```

`.env`에 사이트 URL과 본인 계정 정보를 입력합니다.

4. 실행

```bash
python -m src.main
```

## 주의

- 본인 계정으로 접근 가능한 데이터만 수집합니다.
- 대상 사이트의 이용약관과 로봇/API 정책을 준수합니다.
- 자격 증명과 수집 결과는 Git에 올리지 않습니다.
