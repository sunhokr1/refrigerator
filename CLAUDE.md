# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 현재 상태

`PRD.md`(v0.2)가 요구사항의 기준이다. `PROMPTS.md`의 1~4단계(뼈대 → 기능 → UI → QA)는 모두 끝났고, QA 결과와 수정 이력은 `review_report.md`에 있다. 코드를 바꾸기 전에 `PRD.md`를 먼저 읽을 것. 문서와 UI 문구는 모두 한국어다.

PRD와 일부러 달라진 곳: 추천 버튼은 항상 활성(F-05의 "비활성"과 다름), 요리 종류는 "선택하면 그 종류를 먼저 채우고 모자랄 때만 다른 종류"(F-06). F-24(복사/공유)는 미구현.

## 앱 개요

보유 재료·조리 시간·추가 요청을 입력받아 저녁 메뉴 3개를 추천하는 Streamlit 앱. Streamlit Community Cloud에 배포한다. 기능은 PRD의 ID(F-01~F-26)로 관리하며, 구현 현황을 보고할 때도 이 ID를 쓴다.

## 명령어

```
pip install -r requirements-dev.txt           # 앱 + pytest
streamlit run app.py                          # 실행 (secrets.toml 없이도 대체 추천으로 동작)
pytest                                        # 전체 테스트 (pytest.ini가 루트를 pythonpath로 지정)
pytest tests/test_recommender.py::test_name   # 단일 테스트
```

린터/포매터 설정은 없다. Windows 콘솔(cp949)에서 한글을 출력하는 스크립트나 pytest는 `PYTHONIOENCODING=utf-8`을 붙여야 `UnicodeEncodeError`가 나지 않는다.

테스트 구성: `test_recommender.py`·`test_utils_limits_feedback.py`는 순수 로직, `test_regressions.py`는 QA에서 찾은 버그의 회귀 테스트, `test_app_flows.py`는 Streamlit `AppTest`로 앱 전체를 돌리며 `recommender.recommend_ai`와 `feedback.save_feedback`을 모킹한다(자동 fixture가 `service._cached_ai`와 일일 카운터를 매번 비운다). `AppTest.from_file`은 호출한 파일 기준 상대 경로라 절대 경로를 쓴다.

## 아키텍처

- `app.py`: UI와 `st.session_state`만 담당
- `service.py`: Streamlit 쪽 연결부. 시크릿 읽기, `st.cache_data` 캐싱, 호출 한도, AI 실패 시 대체 추천 전환. `app.py`는 `service.get_recommendations()`만 호출한다
- `recommender.py`, `prompt.py`, `limits.py`, `utils.py`: Streamlit에 의존하지 않는 순수 로직(그래서 pytest로 바로 테스트된다). 모델 ID·토큰 상한·재시도 횟수는 `recommender.py` 상단 상수
- `actions.py`: 피드백 저장·중복 방지 로직(상태를 dict처럼 받아 테스트 가능). 코멘트는 콜백 안에서 `st.session_state`로 읽는다(렌더 시점 값을 `args`로 넘기면 입력 직후 클릭에서 유실됨)
- `ui.py`: CSS와 HTML 조각(카드, 뱃지, 알림). 모델이 만든 문자열은 반드시 `html.escape`를 거쳐 그린다. 실행 중인 서버는 `ui.py` 변경을 반영하지 않으므로(모듈 캐시) 수정 후 서버를 재시작해야 한다
- `feedback.py`: 👍/👎를 Google Sheets에 한 행씩 기록 (`gspread`, RAW 입력 + 수식 인젝션 방지)
- `data/fallback_recipes.json`: 대체 추천 DB(2인분 기준). 재료·양념은 `{name, qty, unit, whole?}`이고 `qty`가 0이면 "약간" 같은 표기다. 보유/부족 구분은 실행 시 `name`으로 계산하고, 표시용 문자열("김치 150g")은 `recommender.format_amount`가 인원수에 맞게 환산해 만든다. 수정하면 `tests/test_recipe_detail.py`가 분량·양념 존재, 시간이 적힌 단계 3개 이상, 비건 태그의 동물성 재료 여부를 검사한다

추천 결과(AI·대체 공통)의 형태는 PRD 8장 스키마에 `match_rate`와 `servings`가 추가된 것이다. 재료 문자열의 분량("돼지고기 150g", "대파 ½대")은 `ingredient_name()`이 떼고 이름만 비교하므로, 분량 표기가 바뀌어도 재료 매칭이 깨지지 않게 유지할 것(분수 기호 ½¼¾도 처리함). 캐시는 AI 성공 결과만 담는다(`_cached_ai`가 실패 시 예외를 던지므로 대체 추천은 캐시되지 않는다).

## 지켜야 할 설계 결정

- **Claude API로 추천**한다(규칙 기반 단독 아님). 규칙 기반은 F-15 대체 추천 용도뿐이다.
- **다국적 요리**다. 한식에 치우친 프롬프트나 양념 가정을 넣지 말 것. 3개 메뉴는 서로 다른 요리 종류/조리법이어야 한다.
- **재료 일치율은 코드에서 직접 계산**한다. LLM이 준 값을 신뢰하지 않는다.
- **앱은 어떤 경우에도 죽지 않아야 한다.** `secrets.toml`이 없거나 API·Sheets가 실패해도 대체 추천으로 동작하고, Sheets 실패는 화면에 노출하지 않고 로그만 남긴다(F-26).
- **비용은 운영자 부담**이다. 호출 한도·입력 상한·출력 토큰 제한·`st.cache_data` 캐싱을 쓰되 "다른 메뉴 보기"는 캐시를 우회한다. 기본 모델은 비용이 낮은 `claude-haiku-5-5`(`recommender.MODEL`)이고, 월 예산 상한 금액은 아직 미결정(PRD 14장, Anthropic 콘솔 한도로 설정).
- **개인정보:** 추천 요청은 저장하지 않고, 사용자가 평가를 누를 때만 PRD 5.4의 컬럼을 익명(UUID 세션 ID)으로 저장한다. 사용자 입력이 `=`, `+`, `-`, `@`로 시작하면 시트 수식으로 해석될 수 있으니 저장 전에 무력화할 것.
- 비밀 값은 `st.secrets`(`ANTHROPIC_API_KEY`, `gcp_service_account`, `SHEET_ID`)로만 읽는다. `.streamlit/secrets.toml`은 커밋하지 않고 `secrets.toml.example`만 둔다.
- Claude 모델 ID는 코드 상단 상수 한 곳에 두고, 값은 추측하지 말고 공식 문서나 `claude-api` 스킬로 확인한다.

## 알아둘 함정

- **추천 버튼은 항상 활성**이다. 입력 직후 포커스가 입력창에 있는 상태에서 비활성 버튼을 누르면 첫 클릭이 사라진다(Streamlit은 포커스를 잃어야 값을 반영). 위젯 값에 의존하는 `on_click` 콜백에서도 같은 문제가 생기니 값은 콜백 안에서 `session_state`로 읽을 것.
- **호출 한도는 두 겹**이다: 세션당 시간당(`MAX_CALLS_PER_HOUR`, 새로고침으로 초기화됨)과 서버 전체 일일(`MAX_CALLS_PER_DAY`, 실제 API 호출만 셈). 입력 상한은 `utils.py`(`MAX_*`)에 모여 있다.
- 기본 양념 판정(`PANTRY`)은 정확 일치다. 부분 일치로 바꾸면 "물만두" 같은 재료가 사라진다.
- 실제 Claude 호출과 Google Sheets 쓰기는 개발 환경에서 검증하지 못했다. 배포 직후 실키로 확인할 것.

## 작업 방식

- 검토(QA)를 요청받으면 먼저 `review_report.md`로 보고하고, 사용자 승인 후에만 수정한다. 수정하면 같은 보고서에 "수정 이력"을 추가한다.
- Playwright로 피드백 저장을 테스트할 때는 실제 운영 시트를 쓰지 말고 `feedback.save_feedback`을 파일 기록 등으로 바꿔 끼운 임시 하네스(또는 테스트용 시트)를 쓴다.
- Playwright 마우스 클릭 테스트는 좌표가 뷰포트 밖이면 조용히 빗나간다. 클릭 전에 `scrollIntoViewIfNeeded()`를 호출하거나 뷰포트를 키울 것.
