"""입력 처리용 순수 함수 모음 (Streamlit에 의존하지 않아 테스트하기 쉽다)."""
import re

COMMON_INGREDIENTS = [
    "계란", "양파", "대파", "마늘", "두부", "감자", "당근", "애호박",
    "김치", "버섯", "닭고기", "돼지고기", "소고기", "참치캔", "밥", "파스타면",
]

QUICK_TAGS = ["매콤하게", "국물 요리", "다이어트", "비건", "아이 동반", "간단하게"]

TIME_OPTIONS = {
    "10분": 10,
    "20분": 20,
    "30분": 30,
    "45분": 45,
    "60분 이상": 60,
}

CUISINES = ["전체", "한식", "양식", "중식", "일식", "동남아"]

# 입력 상한 (토큰 비용 폭주 방지)
MAX_INGREDIENTS = 30
MAX_INGREDIENT_LEN = 30
MAX_INGREDIENT_TEXT_CHARS = 600
MAX_EXTRA_LEN = 200
MAX_EXTRA_INPUT_CHARS = 100


def parse_ingredients(text: str, selected: list[str], max_items: int = MAX_INGREDIENTS) -> list[str]:
    """텍스트(쉼표/줄바꿈 구분)와 멀티셀렉트 값을 합쳐 공백 정리·중복 제거하고 상한을 적용한다."""
    raw = re.split(r"[,\n]", text or "")
    result, seen = [], set()
    for item in [*selected, *raw]:
        name = " ".join(item.split())[:MAX_INGREDIENT_LEN].strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            result.append(name)
            if len(result) >= max_items:
                break
    return result


def build_extra_request(text: str, tags: list[str]) -> str:
    """태그와 자유 입력을 하나의 추가 요청 문자열로 합친다 (길이 상한 적용)."""
    parts = [*tags]
    if text and text.strip():
        parts.append(" ".join(text.split()))
    return ", ".join(parts)[:MAX_EXTRA_LEN]


def has_free_text_request(extra_request: str) -> bool:
    """빠른 선택 태그를 빼고도 직접 입력한 요청이 남아 있는지."""
    rest = extra_request or ""
    for tag in QUICK_TAGS:
        rest = rest.replace(tag, "")
    return bool(re.sub(r"[\s,]+", "", rest))
