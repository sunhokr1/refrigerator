"""Claude 프롬프트와 출력 스키마 (PRD 8장)."""
from utils import MAX_EXTRA_LEN, MAX_INGREDIENT_LEN, MAX_INGREDIENTS

SYSTEM_PROMPT = """\
당신은 집에 있는 재료로 저녁 메뉴를 추천하는 요리 도우미입니다.

규칙:
- 특정 나라에 치우치지 말고 다양한 나라의 가정식·간편식 중에서 추천하세요.
- 메뉴는 정확히 3개이며, 요리 종류(cuisine) 또는 조리법이 서로 달라야 합니다. 사용자가 요리 종류를 지정하면 그 종류를 우선합니다.
- 사용자가 가진 재료를 최대한 활용하세요. 소금, 후추, 설탕, 간장, 식초, 식용유, 올리브오일, 참기름, 고춧가루, 다진 마늘 같은 기본 양념은 이미 있다고 가정합니다.
- 사용자가 입력한 재료만 have_ingredients에 넣고, 입력하지 않은 재료(기본 양념 제외)는 need_ingredients에 넣으세요. need_ingredients는 최소한으로 하세요.
- have_ingredients와 need_ingredients의 모든 항목에는 분량을 붙이세요. 형식은 "재료명 분량"이고 숫자와 단위로 씁니다. 예: "돼지고기 150g", "양파 1/2개", "계란 2개", "밥 2공기". 분량은 사용자가 정한 인원수 기준입니다.
- seasonings에는 요리에 쓰는 기본 양념·기름·물을 분량과 함께 모두 적으세요. 예: "간장 1큰술", "식용유 2큰술", "물 300ml", "소금 약간". 이 양념은 have/need에 중복해서 넣지 마세요.
- 각 메뉴의 소요시간(minutes)은 사용자가 정한 최대 조리 시간을 넘으면 안 됩니다. steps에 적은 시간을 합친 값이 minutes와 크게 어긋나면 안 됩니다.
- 추가 요청(비건, 매운맛, 아이 동반, 다이어트 등)은 반드시 반영하세요. 비건이면 고기, 생선, 계란, 유제품을 쓰지 마세요.
- difficulty는 "쉬움", "보통", "어려움" 중 하나입니다.
- steps는 5~8단계로 쓰고, 처음 요리하는 사람이 그대로 따라 할 수 있게 구체적으로 쓰세요. 각 단계에 다음을 포함하세요.
  · 손질: 써는 크기와 모양(예: "1cm 두께로 채 썬다", "한입 크기로 썬다")
  · 불 세기와 시간: "센 불/중불/약불"과 "3분", "30초"처럼 숫자 시간(예: "중불에서 3분 볶는다")
  · 익은 정도를 알 수 있는 상태(예: "양파가 투명해질 때까지", "가장자리가 노릇해질 때까지")
  · 한 단계에 동작 하나를 기본으로 하고, 면 삶기처럼 동시에 하는 일은 한 단계에 "~하는 동안"으로 묶으세요.
- steps 안에서는 재료를 이름으로만 가리키세요. 분량은 재료 목록(have/need/seasonings)에만 적습니다.
- 모든 텍스트는 한국어로 쓰세요.
- 지정된 JSON 형식으로만 응답하세요.
"""

RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "recipes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "cuisine": {"type": "string"},
                    "summary": {"type": "string"},
                    "minutes": {"type": "integer"},
                    "difficulty": {"type": "string"},
                    "have_ingredients": {"type": "array", "items": {"type": "string"}},
                    "need_ingredients": {"type": "array", "items": {"type": "string"}},
                    "seasonings": {"type": "array", "items": {"type": "string"}},
                    "steps": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "name", "cuisine", "summary", "minutes", "difficulty",
                    "have_ingredients", "need_ingredients", "seasonings", "steps",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["recipes"],
    "additionalProperties": False,
}


def build_user_prompt(
    ingredients: list[str],
    max_minutes: int,
    servings: int,
    extra_request: str,
    cuisine_pref: str | None,
    exclude_names: list[str] | None = None,
) -> str:
    # 호출하는 쪽에서 이미 제한하지만, 비용 폭주를 막기 위해 한 번 더 자른다.
    ingredients = [i[:MAX_INGREDIENT_LEN] for i in ingredients[:MAX_INGREDIENTS]]
    extra_request = (extra_request or "")[:MAX_EXTRA_LEN]
    time_text = "제한 없음(60분 이상 가능)" if max_minutes >= 60 else f"{max_minutes}분 이하"
    lines = [
        f"보유 재료: {', '.join(ingredients)}",
        f"최대 조리 시간: {time_text}",
        f"인원: {servings}명",
        f"요리 종류: {cuisine_pref or '지정 없음(다양하게)'}",
        f"추가 요청: {extra_request or '없음'}",
    ]
    if exclude_names:
        lines.append(f"이미 추천한 메뉴(다시 추천하지 말 것): {', '.join(exclude_names)}")
    lines.append("위 조건에 맞는 저녁 메뉴 3개를 추천해 주세요.")
    return "\n".join(lines)
