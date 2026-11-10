"""호출 횟수 제한 (순수 함수)."""
from datetime import datetime, timedelta, timezone

MAX_CALLS_PER_HOUR = 20      # 세션당 시간당
WINDOW_SECONDS = 3600
MAX_CALLS_PER_DAY = 300      # 서버 전체 하루 상한 (실제 Claude API 호출 기준, 새로고침으로 우회 불가)

KST = timezone(timedelta(hours=9))


def check_and_record(
    call_times: list[float],
    now: float,
    limit: int = MAX_CALLS_PER_HOUR,
    window: int = WINDOW_SECONDS,
) -> tuple[bool, list[float]]:
    """윈도우 안의 호출만 남기고, 한도 이내면 지금 호출을 기록한다.

    반환: (허용 여부, 갱신된 호출 시각 목록)
    """
    recent = [t for t in call_times if now - t < window]
    if len(recent) >= limit:
        return False, recent
    return True, [*recent, now]


def kst_today(now: datetime | None = None) -> str:
    return (now or datetime.now(KST)).astimezone(KST).strftime("%Y-%m-%d")


def check_daily(state: dict, today: str, cap: int = MAX_CALLS_PER_DAY) -> bool:
    """서버 전체 일일 호출 수를 센다. 날짜가 바뀌면 초기화한다. 허용되면 1 증가시키고 True."""
    if state.get("date") != today:
        state["date"], state["count"] = today, 0
    if state["count"] >= cap:
        return False
    state["count"] += 1
    return True
