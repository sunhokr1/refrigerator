"""Google Sheets 피드백 저장 (PRD 5.4). 실패해도 예외를 밖으로 내지 않는다."""
import logging
from datetime import datetime, timedelta, timezone

import streamlit as st

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 오프셋으로 충분
MAX_CELL_LEN = 500
HEADER = [
    "timestamp", "session_id", "ingredients", "max_minutes", "servings",
    "extra_request", "menu_name", "rating", "comment",
]


def sanitize_cell(value) -> str:
    """시트 수식 인젝션 방지: =, +, -, @ 로 시작하면 앞에 '를 붙이고 길이를 제한한다."""
    text = str(value if value is not None else "").replace("\r", " ").strip()[:MAX_CELL_LEN]
    if text and text[0] in "=+-@\t":
        text = "'" + text
    return text


def build_row(
    session_id: str, ingredients: list[str], max_minutes: int, servings: int,
    extra_request: str, menu_name: str, rating: str, comment: str = "",
    now: datetime | None = None,
) -> list[str]:
    ts = (now or datetime.now(KST)).strftime("%Y-%m-%d %H:%M:%S")
    return [
        ts,
        sanitize_cell(session_id),
        sanitize_cell(", ".join(ingredients)),
        str(int(max_minutes)),
        str(int(servings)),
        sanitize_cell(extra_request),
        sanitize_cell(menu_name),
        rating if rating in ("up", "down") else "",
        sanitize_cell(comment),
    ]


@st.cache_resource(show_spinner=False)
def _worksheet():
    import gspread  # 시크릿이 없을 때 불필요한 import 비용을 피한다

    creds = dict(st.secrets["gcp_service_account"])
    return gspread.service_account_from_dict(creds).open_by_key(st.secrets["SHEET_ID"]).sheet1


def is_configured() -> bool:
    try:
        return bool(st.secrets["SHEET_ID"]) and bool(st.secrets["gcp_service_account"])
    except Exception:
        return False


def save_feedback(
    session_id: str, ingredients: list[str], max_minutes: int, servings: int,
    extra_request: str, menu_name: str, rating: str, comment: str = "",
) -> bool:
    """시트에 한 행을 추가한다. 설정이 없거나 실패하면 로그만 남기고 False."""
    if not is_configured():
        return False
    try:
        row = build_row(session_id, ingredients, max_minutes, servings,
                        extra_request, menu_name, rating, comment)
        # RAW: 값을 수식으로 해석하지 않고 문자열 그대로 저장
        _worksheet().append_row(row, value_input_option="RAW")
        return True
    except Exception as e:
        logger.error("피드백 저장 실패: %s", type(e).__name__)
        return False
