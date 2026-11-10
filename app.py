import uuid

import streamlit as st

import actions
import feedback
import service
import ui
from utils import (
    COMMON_INGREDIENTS,
    CUISINES,
    MAX_EXTRA_INPUT_CHARS,
    MAX_INGREDIENT_TEXT_CHARS,
    MAX_INGREDIENTS,
    QUICK_TAGS,
    TIME_OPTIONS,
    build_extra_request,
    has_free_text_request,
    parse_ingredients,
)

st.set_page_config(page_title="냉장고를 부탁해", page_icon="🍳", layout="centered")

NOTICES = {
    "no_key": "AI 추천을 사용할 수 없어 기본 추천 모드로 보여드려요.",
    "limit": "이번 시간의 AI 추천 횟수를 모두 사용했어요. 기본 추천 모드로 보여드려요.",
    "daily_limit": "오늘 AI 추천 한도에 도달했어요. 내일 다시 이용해 주세요. 지금은 기본 추천 모드로 보여드려요.",
    "error": "AI 추천에 문제가 있어 기본 추천 모드로 보여드려요.",
}


def init_state() -> None:
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("round", 0)  # 추천을 새로 받을 때마다 +1 (위젯 키가 라운드마다 달라지게 한다)
    st.session_state.setdefault("history", [])  # 지금까지 추천한 메뉴명 (다른 메뉴 보기용)
    st.session_state.setdefault("last_inputs", None)  # 현재 결과를 만든 입력
    st.session_state.setdefault("rated", set())
    st.session_state.setdefault("pending_down", None)


def render_header() -> None:
    ui.inject_css()
    ui.set_page_lang("ko")
    st.markdown(ui.header_html(), unsafe_allow_html=True)


def note(kind: str, text: str) -> None:
    st.markdown(ui.note_html(kind, text), unsafe_allow_html=True)


def render_inputs() -> dict:
    """입력 위젯을 그리고 정리된 입력값을 반환한다."""
    text = st.text_area(
        "보유 재료",
        placeholder="쉼표나 줄바꿈으로 구분해 입력하세요. 예: 계란, 대파, 김치",
        height=90,
        max_chars=MAX_INGREDIENT_TEXT_CHARS,
    )
    selected = st.multiselect("자주 쓰는 재료에서 고르기", COMMON_INGREDIENTS, placeholder="눌러서 고르기")

    col_time, col_serv = st.columns(2)
    time_label = col_time.select_slider("조리 시간", options=list(TIME_OPTIONS), value="20분")
    servings = col_serv.number_input("인원", min_value=1, max_value=6, value=2, step=1)

    cuisine = st.selectbox("요리 종류", CUISINES)

    tags = st.pills("추가 요청 (빠른 선택)", QUICK_TAGS, selection_mode="multi") or []
    extra_text = st.text_input(
        "추가 요청 (직접 입력)", placeholder="예: 아이도 먹을 수 있게", max_chars=MAX_EXTRA_INPUT_CHARS
    )
    st.markdown('<div class="legal tight">개인정보(이름, 연락처 등)는 입력하지 마세요.</div>', unsafe_allow_html=True)

    return {
        "ingredients": parse_ingredients(text, selected),
        "max_minutes": TIME_OPTIONS[time_label],
        "servings": int(servings),
        "extra_request": build_extra_request(extra_text, tags),
        "cuisine_pref": None if cuisine == "전체" else cuisine,
    }


def run_recommendation(inputs: dict, more: bool = False) -> None:
    """more=True(다른 메뉴 보기)면 직전 추천에 쓴 입력을 그대로 쓰고, 이전 메뉴는 제외한다."""
    exclude = list(st.session_state["history"]) if more else None
    with st.spinner("메뉴를 고르는 중..."):
        result = service.get_recommendations(inputs, exclude)
    st.session_state["result"] = result
    st.session_state["last_inputs"] = inputs
    st.session_state["round"] += 1
    names = [r["name"] for r in result["recipes"]]
    st.session_state["history"] = (st.session_state["history"] + names) if more else names
    st.session_state["pending_down"] = None


def on_rate(menu_name: str, rating: str, comment_key: str | None = None) -> None:
    # 코멘트는 클릭 시점의 위젯 값을 읽는다 (렌더 시점 값을 args로 넘기면 입력 직후 클릭에서 유실된다)
    comment = st.session_state.get(comment_key, "") if comment_key else ""
    actions.record_feedback(st.session_state, feedback.save_feedback, menu_name, rating, comment)


def on_down(menu_name: str) -> None:
    actions.start_down_feedback(st.session_state, menu_name)


def render_feedback(menu_name: str, idx: int) -> None:
    rnd = st.session_state["round"]
    if menu_name in st.session_state["rated"]:
        st.markdown('<div class="legal tight">평가해 주셔서 감사합니다 🙏</div>', unsafe_allow_html=True)
    elif st.session_state["pending_down"] == menu_name:
        comment_key = f"comment_{rnd}_{idx}"
        st.text_input("아쉬운 점을 알려주세요 (선택)", key=comment_key, max_chars=200)
        st.button("의견 보내기", key=f"send_{rnd}_{idx}", on_click=on_rate,
                  args=(menu_name, "down", comment_key), width="stretch")
    else:
        st.markdown('<div class="legal tight">이 추천이 도움이 되었나요?</div>', unsafe_allow_html=True)
        c1, c2, _ = st.columns([3, 3, 2])
        c1.button("👍 도움돼요", key=f"up_{rnd}_{idx}", on_click=on_rate, args=(menu_name, "up"), width="stretch")
        c2.button("👎 아쉬워요", key=f"down_{rnd}_{idx}", on_click=on_down, args=(menu_name,), width="stretch")


def render_results(result: dict, used_inputs: dict) -> None:
    if result["reason"] == "data_missing":
        note("error", "추천 데이터를 불러오지 못했어요. 잠시 후 다시 시도해 주세요. 계속되면 관리자에게 알려 주세요.")
        return
    if result["source"] == "fallback":
        text = NOTICES.get(result["reason"], NOTICES["error"])
        if has_free_text_request(used_inputs["extra_request"]):
            text += " (기본 추천에서는 직접 입력한 요청이 반영되지 않아요.)"
        note("warn" if result["reason"] in ("limit", "daily_limit") else "info", text)
    if result.get("cuisine_mixed"):
        note("info", f"'{used_inputs['cuisine_pref']}' 메뉴가 부족해 다른 종류도 함께 보여드려요.")
    if result.get("repeated"):
        note("info", "새로 추천할 메뉴가 부족해 이전에 보여드린 메뉴가 다시 나왔어요.")
    if not result["recipes"]:
        note("warn", "조건에 맞는 메뉴를 찾지 못했어요. 재료를 더 추가하거나 조건을 바꿔 보세요.")
        return

    for i, r in enumerate(result["recipes"], start=1):
        with st.container(border=True):
            st.markdown(ui.recipe_header_html(i, r), unsafe_allow_html=True)
            with st.expander("조리 순서", expanded=(i == 1)):
                for n, step in enumerate(r["steps"], start=1):
                    st.markdown(f"{n}. {ui.format_step(step)}")
            render_feedback(r["name"], i)


def render_footer() -> None:
    st.divider()
    st.markdown(ui.legal_html(), unsafe_allow_html=True)


def main() -> None:
    init_state()
    render_header()
    with st.container(border=True):
        inputs = render_inputs()
        if len(inputs["ingredients"]) >= MAX_INGREDIENTS:
            st.markdown(f'<div class="legal tight">재료는 최대 {MAX_INGREDIENTS}개까지 반영돼요.</div>', unsafe_allow_html=True)
        # 버튼은 항상 활성: 입력 직후 첫 클릭이 사라지는 문제를 피한다. 재료가 비면 경고만 보여준다.
        clicked = st.button("🍽️ 메뉴 추천받기", type="primary", width="stretch")
        if clicked and not inputs["ingredients"]:
            note("warn", "보유 재료를 한 가지 이상 입력하거나 선택해 주세요.")

    if clicked and inputs["ingredients"]:
        run_recommendation(inputs)

    result = st.session_state["result"]
    used_inputs = st.session_state["last_inputs"]
    if not result:
        st.markdown(ui.empty_state_html(), unsafe_allow_html=True)
    else:
        if inputs != used_inputs and inputs["ingredients"]:
            note("info", "입력이 바뀌었어요. 새 조건으로 보려면 '메뉴 추천받기'를 눌러 주세요.")
        render_results(result, used_inputs)
        if st.button("🔄 다른 메뉴 보기", width="stretch"):
            run_recommendation(used_inputs, more=True)
            st.rerun()

    render_footer()


main()
