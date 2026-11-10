"""Streamlit 쪽 연결부: 시크릿, 캐싱, 호출 한도, AI→대체 추천 전환."""
import logging
import threading
import time

import streamlit as st

import limits
import recommender

logger = logging.getLogger(__name__)


class DailyLimitReached(Exception):
    """서버 전체 일일 호출 상한에 도달."""


def get_secret(name: str):
    """secrets.toml이 없거나 키가 없어도 예외 없이 None."""
    try:
        return st.secrets[name]
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def _daily_counter() -> dict:
    return {"date": "", "count": 0, "lock": threading.Lock()}


def _reserve_daily_call() -> bool:
    """실제 Claude 호출 1회분을 서버 전체 일일 상한에서 예약한다 (새로고침으로 우회할 수 없다)."""
    counter = _daily_counter()
    with counter["lock"]:
        return limits.check_daily(counter, limits.kst_today())


def _guarded_ai(ingredients, max_minutes, servings, extra_request, cuisine_pref, exclude_names=None):
    if not _reserve_daily_call():
        raise DailyLimitReached()
    recipes = recommender.recommend_ai(
        get_secret("ANTHROPIC_API_KEY"),
        list(ingredients), max_minutes, servings, extra_request, cuisine_pref, exclude_names,
    )
    logger.info("AI 추천 성공")
    return recipes


@st.cache_data(ttl=3600, max_entries=200, show_spinner=False)
def _cached_ai(
    ingredients: tuple[str, ...],
    max_minutes: int,
    servings: int,
    extra_request: str,
    cuisine_pref: str | None,
) -> list[dict]:
    # 실패하면 예외가 나므로 실패 결과는 캐시되지 않는다. 키는 인자에 넣지 않는다(캐시 키 노출 방지).
    # 이 함수 본문은 캐시에 없을 때만 실행되므로 일일 상한은 실제 API 호출만 센다.
    return _guarded_ai(ingredients, max_minutes, servings, extra_request, cuisine_pref)


def get_recommendations(inputs: dict, exclude_names: list[str] | None = None) -> dict:
    """추천 결과를 반환한다.

    반환: {"recipes": [...], "source": "ai" | "fallback",
           "reason": None | "no_key" | "limit" | "daily_limit" | "error" | "data_missing"(대체 레시피 파일 없음, recipes는 빈 목록),
           "repeated": 이전에 추천한 메뉴가 다시 섞였는지, "cuisine_mixed": 선택한 요리 종류가 부족해 다른 종류가 섞였는지}
    "다른 메뉴 보기"(exclude_names 있음)는 캐시를 우회한다.
    """
    def finish(recipes: list[dict], source: str, reason: str | None) -> dict:
        cuisine = inputs["cuisine_pref"]
        recipes = [{**r, "servings": inputs["servings"]} for r in recipes]  # 분량 표시 기준 인원수
        return {
            "recipes": recipes, "source": source, "reason": reason,
            "repeated": bool(exclude_names) and any(r["name"] in exclude_names for r in recipes),
            "cuisine_mixed": source == "fallback" and bool(cuisine) and any(r["cuisine"] != cuisine for r in recipes),
        }

    def fallback(reason: str) -> dict:
        try:
            recipes = recommender.recommend_fallback(
                inputs["ingredients"], inputs["max_minutes"], inputs["extra_request"],
                inputs["cuisine_pref"], exclude_names, servings=inputs["servings"],
            )
        except recommender.FallbackDataError:
            # 배포 시 레시피 파일 누락 등. 앱을 죽이지 않고 안내만 보여준다(상세는 recommender가 로그로 남김).
            return {"recipes": [], "source": "fallback", "reason": "data_missing",
                    "repeated": False, "cuisine_mixed": False}
        return finish(recipes, "fallback", reason)

    if not get_secret("ANTHROPIC_API_KEY"):
        return fallback("no_key")

    allowed, st.session_state["call_times"] = limits.check_and_record(
        st.session_state.get("call_times", []), time.time()
    )
    if not allowed:
        return fallback("limit")

    try:
        if exclude_names:
            recipes = _guarded_ai(
                inputs["ingredients"], inputs["max_minutes"], inputs["servings"],
                inputs["extra_request"], inputs["cuisine_pref"], exclude_names,
            )
        else:
            recipes = _cached_ai(
                tuple(sorted(inputs["ingredients"])), inputs["max_minutes"], inputs["servings"],
                inputs["extra_request"], inputs["cuisine_pref"],
            )
        return finish(recipes, "ai", None)
    except DailyLimitReached:
        return fallback("daily_limit")
    except recommender.RecommendError:
        return fallback("error")
    except Exception:  # 예상 밖 오류도 앱을 죽이지 않는다 (상세는 로그로만)
        logger.exception("추천 중 예상하지 못한 오류")
        return fallback("error")
