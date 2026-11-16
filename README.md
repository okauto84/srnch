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

3. 비밀 변수는 Streamlit Cloud Secrets에 등록합니다.
   (`SUPABASE_PROJECT`, `SUPABASE_KEY`, `W_DIMODE_URL`, `W_DIMODE_ID`, `W_DIMODE_PW`, `W_DIMODE_URL_MEMBERS`, `ADMIN_PW`)

4. 실행

```bash
streamlit run index.py
```

## 주의

- 본인 계정으로 접근 가능한 데이터만 수집합니다.
- 대상 사이트의 이용약관과 로봇/API 정책을 준수합니다.
- URL/ID/PW 등 비밀 값은 코드와 Git에 넣지 않습니다.
