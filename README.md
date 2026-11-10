# 냉장고를 부탁해

보유 재료, 조리 시간, 추가 요청을 입력하면 저녁 메뉴를 추천해 주는 Streamlit 앱입니다. 자세한 요구사항은 `PRD.md`를 참고하세요.

## 실행

```
pip install -r requirements.txt
streamlit run app.py
```

개발 중에는 `ui.py`를 고친 뒤 서버를 재시작해야 반영됩니다(모듈 캐시).

## 테스트

```
pip install -r requirements-dev.txt
pytest                                          # 전체
pytest tests/test_recommender.py::test_name     # 단일
```

## 설정

`.streamlit/secrets.toml.example`을 `.streamlit/secrets.toml`로 복사해 값을 채웁니다. `secrets.toml`은 커밋하지 않습니다.

| 값 | 용도 | 없을 때 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude 추천 | 내장 레시피 DB로 대체 추천 |
| `SHEET_ID`, `gcp_service_account` | 👍/👎 피드백을 Google Sheets에 저장 | 피드백 저장을 건너뜀 |

### 1. Anthropic 키와 비용 한도
1. Anthropic 콘솔에서 API 키를 발급해 `ANTHROPIC_API_KEY`에 넣습니다.
2. **콘솔에서 월 사용 한도를 설정**하세요(PRD 10장 7번). 키는 운영자 계정으로 과금됩니다.
3. 앱 안의 방어선(상수로 조절): 세션당 시간당 20회(`limits.py`의 `MAX_CALLS_PER_HOUR`), **서버 전체 하루 300회**(`MAX_CALLS_PER_DAY`, 새로고침으로 우회 불가), 입력 상한(재료 30개, 항목당 30자, 추가 요청 200자), 출력 토큰 6,000.
4. 사용 모델은 `recommender.py`의 `MODEL`, 시간 제한은 `TIMEOUT_SECONDS`(20초)/`TOTAL_BUDGET_SECONDS`(30초)입니다. 분량·시간이 든 상세 레시피를 만들어 출력이 길어서 이 값으로 잡았으니, 실제 응답 시간을 보고 조절하세요.

### 2. Google Sheets 피드백
1. Google Cloud에서 프로젝트를 만들고 **Google Sheets API를 활성화**합니다.
2. **서비스 계정**을 만들고 JSON 키를 발급합니다. 이 JSON 내용을 `secrets.toml`의 `[gcp_service_account]`에 옮깁니다.
3. 피드백용 Google Sheet를 만들고 첫 행에 아래 헤더를 넣은 뒤, 서비스 계정 이메일(`client_email`)에 **편집 권한으로 공유**합니다. 시트는 비공개로 유지하세요.
   `timestamp, session_id, ingredients, max_minutes, servings, extra_request, menu_name, rating, comment`
4. 시트 주소의 ID를 `SHEET_ID`에 넣습니다.

### 3. 배포 (Streamlit Community Cloud)
1. GitHub에 올립니다(`secrets.toml`, `.playwright-mcp/`은 `.gitignore`에 있음).
2. Community Cloud에서 저장소를 연결하고 메인 파일을 `app.py`로 지정합니다.
3. Advanced settings → Secrets에 `secrets.toml` 내용을 붙여 넣습니다.
4. **배포 직후 실제 키로 한 번 추천을 받아 "기본 추천 모드" 안내가 뜨지 않는지 확인하세요.** API 호출이 거부되면 앱은 조용히 대체 추천으로 넘어가므로, 확인하지 않으면 AI가 한 번도 안 쓰이는 줄 모를 수 있습니다(서버 로그에 `Claude 호출 실패`가 남습니다).

## 운영 시 주의
- `ANTHROPIC_LOG=debug` 같은 SDK 디버그 로그를 켜면 사용자 입력이 담긴 요청 본문이 로그에 남습니다. 운영에서는 켜지 마세요.
- 대체 추천 모드에서는 직접 입력한 요청 문장이 반영되지 않습니다(빠른 선택 태그만 반영). 인원수는 재료·양념 분량 환산에 반영됩니다.
- 페이지 `lang`은 Streamlit이 `en`으로 고정하는데, 앱이 `ko`로 바꿉니다. 브라우저 환경에 따라 적용되지 않을 수 있습니다.
