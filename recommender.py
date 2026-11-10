"""메뉴 추천: Claude 호출, 응답 검증, 재료 일치율 계산, 대체 추천.

Streamlit에 의존하지 않는다(키는 호출하는 쪽에서 넘겨준다).
"""
import json
import logging
import re
import time
from pathlib import Path

import anthropic

from prompt import RECIPE_SCHEMA, SYSTEM_PROMPT, build_user_prompt
from utils import QUICK_TAGS

logger = logging.getLogger(__name__)

# 비용이 낮은 모델을 기본값으로 쓴다. 품질이 부족하면 이 값만 바꾸면 된다.
MODEL = "claude-haiku-5-5"
MAX_TOKENS = 6000
EFFORT = "low"
TIMEOUT_SECONDS = 20.0        # 한 번의 호출 제한 (분량·시간이 든 상세 레시피라 출력이 길다)
TOTAL_BUDGET_SECONDS = 30.0   # 재시도를 포함한 전체 상한
MIN_ATTEMPT_SECONDS = 3.0     # 남은 시간이 이보다 짧으면 재시도하지 않는다
MAX_ATTEMPTS = 2              # 최초 1회 + 재시도 1회
RECIPE_COUNT = 3
MAX_RECIPE_MINUTES = 600
NO_TIME_LIMIT_MINUTES = 60    # "60분 이상"은 시간 제한 없음으로 취급
MAX_PER_CUISINE = 2           # 대체 추천에서 한 요리 종류가 차지할 수 있는 최대 개수 (다양성)

FALLBACK_NAME = "fallback_recipes.json"
BASE_DIR = Path(__file__).parent
FALLBACK_PATH = BASE_DIR / "data" / FALLBACK_NAME
# 배포할 때 data 폴더 없이 올라가도 찾을 수 있게 앱 파일 옆도 본다.
FALLBACK_CANDIDATES = [FALLBACK_PATH, BASE_DIR / FALLBACK_NAME]

# 이미 있다고 가정하는 기본 양념 (일치율 계산에서 제외). 이름이 정확히 같을 때만 양념으로 본다.
PANTRY = {
    "소금", "후추", "후춧가루", "설탕", "간장", "식초", "식용유", "올리브오일", "올리브유", "참기름",
    "들기름", "고춧가루", "다진 마늘", "물", "물엿", "깨", "참깨", "맛술", "미림", "굴소스",
    "케첩", "마요네즈", "된장", "고추장", "버터", "밀가루", "전분",
}

# 같은 재료의 다른 표기
SYNONYMS = {"달걀": "계란", "고추가루": "고춧가루", "후춧가루": "후추"}
_QTY_WORDS = {"약간", "조금", "적당량", "적당히", "소량"}


class RecommendError(Exception):
    """AI 추천 실패 (호출 측에서 대체 추천으로 전환한다)."""


class FallbackDataError(Exception):
    """대체 추천용 레시피 파일이 없거나 읽을 수 없음 (배포 시 파일 누락 등)."""


# ---------------------------------------------------------------- 재료 매칭

def _norm(text: str) -> str:
    return "".join(text.lower().split())


def _canon(text: str) -> str:
    n = _norm(text)
    for old, new in SYNONYMS.items():
        n = n.replace(old, new)
    return n


def ingredient_name(item: str) -> str:
    """'돼지고기 100g', '다진 소고기 200g', '소금 약간' 같은 표기에서 수량을 떼고 이름만 남긴다."""
    tokens = [t for t in item.split() if not re.search(r"[\d½¼¾⅓⅔]", t) and t not in _QTY_WORDS]
    name = re.sub(r"[()\[\]]", "", " ".join(tokens))
    return _canon(name) or _canon(item)


_PANTRY_CANON = {_canon(p) for p in PANTRY}


def _is_pantry(item: str) -> bool:
    return ingredient_name(item) in _PANTRY_CANON


def _covered(item: str, user_canon: list[str]) -> bool:
    """재료가 사용자 보유 재료와 겹치는지. 1글자 재료('밥', '김', '파')는 정확히 같을 때만 인정한다."""
    n = ingredient_name(item)
    for u in user_canon:
        if not u or not n:
            continue
        if u == n:
            return True
        if len(u) >= 2 and (n.endswith(u) or n.startswith(u)):
            return True
        if len(n) >= 2 and (u.endswith(n) or u.startswith(n)):
            return True
    return False


def split_have_need(items: list[str], user_ingredients: list[str]) -> tuple[list[str], list[str]]:
    """필요 재료를 보유/부족으로 나눈다. 기본 양념은 양쪽에서 제외한다."""
    user_canon = [_canon(u) for u in user_ingredients]
    have, need = [], []
    for item in items:
        if _is_pantry(item):
            continue
        (have if _covered(item, user_canon) else need).append(item)
    return have, need


def match_rate(have: list[str], need: list[str]) -> float:
    total = len(have) + len(need)
    return len(have) / total if total else 1.0


# ---------------------------------------------------------------- 응답 검증

def clean_text(value: str) -> str:
    """모델이 만든 문자열에서 마크다운 이미지·링크와 HTML 태그를 제거한다 (외부 요청/추적 방지)."""
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    value = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    return value.strip()


def _as_str_list(value) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("목록 필드가 아님")
    cleaned = (clean_text(str(v)) for v in value)
    return [v for v in cleaned if v]


def validate_recipes(
    data,
    max_minutes: int,
    user_ingredients: list[str],
    exclude_names: list[str] | None = None,
) -> list[dict]:
    """모델 응답을 검증·정리한다. 문제가 있으면 ValueError."""
    if not isinstance(data, dict) or not isinstance(data.get("recipes"), list):
        raise ValueError("recipes 필드가 없음")

    excluded = {_norm(n) for n in (exclude_names or [])}
    seen: set[str] = set()
    recipes = []
    for raw in data["recipes"]:
        if not isinstance(raw, dict):
            raise ValueError("레시피 항목이 객체가 아님")
        fields = {}
        for key in ("name", "cuisine", "summary", "difficulty"):
            value = raw.get(key)
            fields[key] = clean_text(value) if isinstance(value, str) else ""
            if not fields[key]:
                raise ValueError(f"필수 필드 누락: {key}")

        minutes = raw.get("minutes")
        if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes != int(minutes):
            raise ValueError("minutes가 정수가 아님")
        minutes = int(minutes)
        if not 1 <= minutes <= MAX_RECIPE_MINUTES:
            raise ValueError(f"minutes 범위 오류: {minutes}")
        if max_minutes < NO_TIME_LIMIT_MINUTES and minutes > max_minutes:
            raise ValueError(f"시간 초과: {fields['name']} {minutes}분")

        key_name = _norm(fields["name"])
        if key_name in excluded:
            raise ValueError(f"이미 추천한 메뉴: {fields['name']}")
        if key_name in seen:
            raise ValueError(f"중복 메뉴명: {fields['name']}")
        seen.add(key_name)

        steps = _as_str_list(raw.get("steps"))
        if not steps:
            raise ValueError("steps가 비어 있음")
        # 양념(분량 포함)은 선택 필드다. 없거나 형식이 이상해도 추천 자체는 살린다.
        try:
            seasonings = _as_str_list(raw.get("seasonings", []))
        except ValueError:
            seasonings = []

        # 모델이 나눈 보유/부족을 믿지 않고 사용자 입력 기준으로 다시 나눈다.
        claimed = _as_str_list(raw.get("have_ingredients")) + _as_str_list(raw.get("need_ingredients"))
        have, need = split_have_need(claimed, user_ingredients)
        recipes.append({
            **fields,
            "minutes": minutes,
            "have_ingredients": have,
            "need_ingredients": need,
            "seasonings": seasonings,
            "steps": steps,
            "match_rate": match_rate(have, need),
        })

    if len(recipes) < RECIPE_COUNT:
        raise ValueError(f"메뉴가 {len(recipes)}개뿐임")
    return recipes[:RECIPE_COUNT]


# ---------------------------------------------------------------- AI 추천

def _call_claude(api_key: str, user_prompt: str, timeout: float = TIMEOUT_SECONDS) -> dict:
    client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": RECIPE_SCHEMA},
        },
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise ValueError(f"응답이 완료되지 않음: {response.stop_reason}")
    text = "".join(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def recommend_ai(
    api_key: str,
    ingredients: list[str],
    max_minutes: int,
    servings: int,
    extra_request: str,
    cuisine_pref: str | None,
    exclude_names: list[str] | None = None,
) -> list[dict]:
    """Claude로 추천한다. 검증 실패·타임아웃은 시간 예산 안에서 1회 재시도하고, 끝내 실패하면 RecommendError."""
    user_prompt = build_user_prompt(
        ingredients, max_minutes, servings, extra_request, cuisine_pref, exclude_names
    )
    started = time.monotonic()
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        timeout = min(TIMEOUT_SECONDS, TOTAL_BUDGET_SECONDS - (time.monotonic() - started))
        if timeout < MIN_ATTEMPT_SECONDS:
            break
        try:
            data = _call_claude(api_key, user_prompt, timeout=timeout)
            return validate_recipes(data, max_minutes, ingredients, exclude_names)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                anthropic.NotFoundError, anthropic.BadRequestError) as e:
            # 재시도해도 소용없는 오류 (키/모델/요청 형식 문제). 키는 로그에 남기지 않는다.
            logger.error("Claude 호출 실패(재시도 안 함): %s %s", type(e).__name__,
                         str(getattr(e, "message", ""))[:200])
            raise RecommendError(type(e).__name__) from e
        except (anthropic.APIError, ValueError) as e:
            last_error = e
            logger.warning("추천 시도 %d/%d 실패: %s", attempt, MAX_ATTEMPTS, type(e).__name__)
    raise RecommendError(type(last_error).__name__ if last_error else "Timeout") from last_error


# ---------------------------------------------------------------- 대체 추천

def load_fallback_recipes(path: Path | None = None) -> list[dict]:
    """대체 레시피를 읽는다. 없거나 깨져 있으면 FallbackDataError (서버 로그에 찾은 위치와 폴더 내용을 남긴다)."""
    candidates = [Path(path)] if path else FALLBACK_CANDIDATES
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            with open(candidate, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            logger.error("대체 레시피 파일을 읽지 못함: %s (%s)", candidate, type(e).__name__)
            raise FallbackDataError(f"{candidate.name} 읽기 실패") from e
        if not isinstance(data, list) or not data:
            logger.error("대체 레시피 파일 형식 오류(비어 있거나 목록이 아님): %s", candidate)
            raise FallbackDataError(f"{candidate.name} 형식 오류")
        return data

    def listing(directory: Path) -> list[str]:
        try:
            return sorted(p.name for p in directory.iterdir())
        except OSError:
            return ["(폴더 없음)"]

    logger.error(
        "대체 레시피 파일을 찾지 못함. 찾아본 위치=%s | 앱 폴더 내용=%s | data 폴더 내용=%s",
        [str(c) for c in candidates], listing(BASE_DIR), listing(BASE_DIR / "data"),
    )
    raise FallbackDataError(f"{FALLBACK_NAME} 없음")


def _diversify(ordered: list, n: int, max_per_cuisine: int) -> list:
    """점수 순서를 지키되 한 요리 종류가 max_per_cuisine개를 넘지 않게 고른다. 모자라면 나머지로 채운다."""
    picked, counts = [], {}
    for item in ordered:
        c = item[1]["cuisine"]
        if counts.get(c, 0) < max_per_cuisine:
            picked.append(item)
            counts[c] = counts.get(c, 0) + 1
        if len(picked) == n:
            return picked
    for item in ordered:
        if item not in picked:
            picked.append(item)
        if len(picked) == n:
            break
    return picked


_FRACTIONS = {0.25: "¼", 0.5: "½", 0.75: "¾"}


def _as_item(entry) -> dict:
    """DB의 재료 항목을 {name, qty, unit, whole} 형태로 통일한다 (문자열만 있는 옛 형식도 허용)."""
    return {"name": entry, "qty": None, "unit": ""} if isinstance(entry, str) else entry


def _fmt_qty(value: float) -> str:
    """1.5 → '1½', 0.25 → '¼', 200 → '200'."""
    whole, frac = int(value), round(value - int(value), 2)
    if frac == 0:
        return str(whole)
    symbol = _FRACTIONS.get(frac)
    if symbol is None:
        return f"{value:g}"
    return f"{whole}{symbol}" if whole else symbol


def scale_qty(qty: float, factor: float, unit: str, whole: bool = False) -> float:
    """인원수에 맞게 분량을 환산한다. g/ml는 5·10·50 단위로, 나머지는 ¼·½ 단위로 반올림한다."""
    value = qty * factor
    if whole:  # 계란·마늘 쪽처럼 쪼갤 수 없는 재료
        return float(max(1, int(value + 0.5)))
    if unit in ("g", "ml"):
        step = 5 if value < 50 else 10 if value < 500 else 50
        return float(max(step, round(value / step) * step))
    step = 0.25 if value < 1 else 0.5
    return max(step, round(value / step) * step)


def format_amount(entry, factor: float = 1.0) -> str:
    """'김치 150g', '계란 2개', '후추 약간' 형태의 문자열로 만든다."""
    item = _as_item(entry)
    name, qty, unit = item["name"], item.get("qty"), item.get("unit", "")
    if not qty:  # 약간/적당량
        return f"{name} {unit}".strip()
    value = qty if factor == 1 else scale_qty(qty, factor, unit, item.get("whole", False))
    return f"{name} {_fmt_qty(value)}{unit}"


def recommend_fallback(
    ingredients: list[str],
    max_minutes: int,
    extra_request: str,
    cuisine_pref: str | None,
    exclude_names: list[str] | None = None,
    recipes: list[dict] | None = None,
    servings: int = 2,
) -> list[dict]:
    """내장 레시피 DB에서 재료 일치율·시간·태그로 점수를 매겨 상위 3개를 고른다.

    요리 종류를 지정하면 그 종류를 먼저 채우고, 모자랄 때만 다른 종류로 채운다.
    재료·양념 분량은 인원수(servings)에 맞게 환산해서 돌려준다(DB는 2인분 기준).
    """
    pool = recipes if recipes is not None else load_fallback_recipes()
    excluded = {_norm(n) for n in (exclude_names or [])}
    request = extra_request or ""
    wanted_tags = [t for t in QUICK_TAGS if t in request or (t == "국물 요리" and "국물" in request)]
    time_limited = max_minutes < NO_TIME_LIMIT_MINUTES

    scored = []
    for r in pool:
        if time_limited and r["minutes"] > max_minutes:
            continue
        if "비건" in wanted_tags and "비건" not in r.get("tags", []):
            continue  # 비건 요청은 조건을 만족하는 것만
        have, need = split_have_need([_as_item(i)["name"] for i in r["ingredients"]], ingredients)
        if not have:
            continue  # 보유 재료를 하나도 못 쓰면 제외
        score = match_rate(have, need) * 10
        score += 2 * sum(1 for t in wanted_tags if t in r.get("tags", []))
        scored.append((score, r, have, need))

    scored.sort(key=lambda x: (-x[0], x[1]["minutes"], x[1]["name"]))
    fresh = [s for s in scored if _norm(s[1]["name"]) not in excluded]
    candidates = fresh or scored  # 새 메뉴가 남지 않으면 처음부터 다시
    if cuisine_pref:
        ordered = ([s for s in candidates if s[1]["cuisine"] == cuisine_pref]
                   + [s for s in candidates if s[1]["cuisine"] != cuisine_pref])
        picked = ordered[:RECIPE_COUNT]
    else:
        picked = _diversify(candidates, RECIPE_COUNT, MAX_PER_CUISINE)
    result = []
    for _, r, have, need in picked:
        factor = servings / (r.get("servings") or 2)
        shown = {i["name"]: format_amount(i, factor) for i in map(_as_item, r["ingredients"])}
        result.append({
            "name": r["name"], "cuisine": r["cuisine"], "summary": r["summary"],
            "minutes": r["minutes"], "difficulty": r["difficulty"], "servings": servings,
            "have_ingredients": [shown.get(n, n) for n in have],
            "need_ingredients": [shown.get(n, n) for n in need],
            "seasonings": [format_amount(s, factor) for s in r.get("seasonings", [])],
            "steps": r["steps"],
            "match_rate": match_rate(have, need),
        })
    return result
