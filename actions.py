"""피드백 처리 로직 (Streamlit 위젯과 분리해 테스트할 수 있게 한다).

state는 dict처럼 동작하는 객체(st.session_state 또는 테스트용 dict)다.
"""


def record_feedback(state, save_fn, menu_name: str, rating: str, comment: str = "") -> bool:
    """평가를 저장하고 '평가 완료'로 표시한다. 이미 평가한 메뉴면 아무것도 하지 않고 False."""
    if menu_name in state["rated"]:
        return False
    inp = state["last_inputs"]
    save_fn(
        state["session_id"], inp["ingredients"], inp["max_minutes"], inp["servings"],
        inp["extra_request"], menu_name, rating, comment,
    )
    state["rated"].add(menu_name)
    state["pending_down"] = None
    return True


def start_down_feedback(state, menu_name: str) -> None:
    """👎를 누르면 코멘트 입력 단계로 넘어간다 (이미 평가한 메뉴는 무시)."""
    if menu_name not in state["rated"]:
        state["pending_down"] = menu_name
