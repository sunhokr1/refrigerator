"""화면 꾸미기 전용 모듈 (CSS와 HTML 조각). 추천/저장 로직은 여기에 두지 않는다.

LLM이 만든 문자열을 HTML로 그리므로 반드시 html.escape를 거친다.
"""
import re
from html import escape

import streamlit as st

# 색상 (글자/배경 대비 4.5:1 이상으로 고른 값)
PRIMARY = "#C2410C"
INK = "#2B2118"
MUTED = "#6B5B4D"
LINE = "#F0DFCB"

CSS = f"""
<style>
.stApp, .stApp p, .stApp label, .stApp li, .stApp button, .stApp input, .stApp textarea, .stApp h1 {{
  font-family: "Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
}}
/* 아이콘 폰트는 덮어쓰지 않는다 (덮어쓰면 아이콘 이름이 글자로 보인다) */
.stApp [data-testid="stIconMaterial"], .stApp span[class*="material"] {{
  font-family: "Material Symbols Rounded", "Material Symbols Outlined" !important;
}}
/* 한글은 단어(띄어쓰기) 단위로 줄바꿈한다. 너무 긴 단어만 강제로 자른다. */
.stApp p, .stApp li {{ word-break: keep-all; overflow-wrap: break-word; }}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{ display: none; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ max-width: 680px; padding: 1.5rem 1rem 3rem; }}

/* 헤더 */
.app-hero {{ text-align: center; padding: 0.5rem 0 1.25rem; }}
.app-hero .logo {{ font-size: 2.6rem; line-height: 1; }}
.app-hero h1 {{ font-size: 1.9rem; margin: 0.25rem 0 0.2rem; padding: 0; color: {INK}; letter-spacing: -0.02em; }}
.app-hero p {{ margin: 0; color: {MUTED}; font-size: 1rem; }}

/* 카드(테두리 컨테이너) */
[data-testid="stVerticalBlockBorderWrapper"] {{
  background: #FFFFFF; border: 1px solid {LINE}; border-radius: 16px;
  box-shadow: 0 1px 3px rgba(120, 70, 20, 0.06);
}}

/* 버튼: 터치 영역 44px 이상 */
.stButton > button, .stFormSubmitButton > button {{
  min-height: 46px; border-radius: 12px; font-weight: 600;
}}
.stButton > button[kind="primary"] {{
  min-height: 52px; font-size: 1.05rem; font-weight: 700;
}}
.stButton > button:disabled {{
  background: #E9DFD3; color: #6B5B4D; border-color: #E9DFD3; cursor: not-allowed;
}}
[data-testid="stButtonGroup"] button {{ min-height: 40px; padding: 0 1rem; }}
.stButton > button:focus-visible {{ outline: 3px solid #1D4ED8; outline-offset: 2px; }}

/* 결과 카드 */
.recipe-title {{ font-size: 1.2rem; font-weight: 700; color: {INK}; margin: 0 0 0.45rem; line-height: 1.35; }}
.recipe-title .no {{ color: {PRIMARY}; margin-right: 0.35rem; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.6rem; }}
.badge {{ display: inline-block; padding: 0.15rem 0.65rem; border-radius: 999px; font-size: 0.82rem;
          font-weight: 600; background: #F6EBDD; color: #5A3A1C; }}
.badge.cuisine {{ background: {PRIMARY}; color: #FFFFFF; }}
.recipe-summary {{ color: {MUTED}; margin: 0 0 0.75rem; }}

.match {{ margin: 0.2rem 0 0.9rem; }}
.match .label {{ display: flex; justify-content: space-between; font-size: 0.85rem; color: {MUTED}; margin-bottom: 0.25rem; }}
.match .label b {{ color: {INK}; }}
.match .track {{ height: 8px; border-radius: 999px; background: #F1E6D8; overflow: hidden; }}
.match .fill {{ height: 100%; border-radius: 999px; background: #2F855A; }}
.match .fill.mid {{ background: #D97706; }}
.match .fill.low {{ background: #C2410C; }}

.ing-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem; margin-bottom: 0.55rem; }}
.ing-row .head {{ font-size: 0.85rem; font-weight: 700; color: {INK}; margin-right: 0.25rem; }}
.chip {{ padding: 0.12rem 0.6rem; border-radius: 8px; font-size: 0.88rem; }}
.chip.have {{ background: #E6F4EA; color: #1B5E34; }}
.chip.need {{ background: #FFE9D6; color: #8A3410; }}
.chip.season {{ background: #F3EDE4; color: #4E3F31; }}
.chip.none {{ background: transparent; color: {MUTED}; padding-left: 0; }}
.servings-note {{ font-size: 0.8rem; color: {MUTED}; margin: -0.2rem 0 0.5rem; }}

/* 상태 메시지 */
.note {{ border-radius: 12px; padding: 0.75rem 1rem; margin: 0.5rem 0 1rem; font-size: 0.95rem; border-left: 5px solid; }}
.note.info {{ background: #EEF5FF; border-color: #2563EB; color: #1E3A8A; }}
.note.warn {{ background: #FFF6DB; border-color: #D97706; color: #7A4A00; }}
.note.error {{ background: #FDECEC; border-color: #C53030; color: #7A1D1D; }}
.empty {{ text-align: center; color: {MUTED}; padding: 1.5rem 1rem; }}
.empty .big {{ font-size: 2rem; }}
.empty b {{ color: {INK}; }}

/* 하단 고지 */
.legal {{ color: {MUTED}; font-size: 0.8rem; line-height: 1.5; margin-top: 0.25rem; }}
.legal.tight {{ margin: 0 0 0.75rem; }}
iframe[height="1"] {{ display: block; height: 1px; border: 0; opacity: 0; }}

@media (max-width: 480px) {{
  .block-container {{ padding: 1rem 0.75rem 2.5rem; }}
  .app-hero h1 {{ font-size: 1.6rem; }}
  .recipe-title {{ font-size: 1.1rem; }}
}}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def set_page_lang(lang: str = "ko") -> None:
    """Streamlit은 <html lang="en">을 고정하므로, 스크린리더가 한국어로 읽도록 값을 바꾼다 (실패해도 무시).

    고정된 문자열만 넣는다. st.iframe은 JS를 실행하므로 사용자·모델 입력을 절대 넣지 말 것.
    """
    st.iframe(
        f"<script>try{{window.parent.document.documentElement.lang='{lang}'}}catch(e){{}}</script>",
        height=1,
    )


def escape_md(text: str) -> str:
    """st.markdown에 넣기 전에 달러 기호를 이스케이프한다 ($...$가 수식으로 렌더링되는 것을 막는다)."""
    return text.replace("$", "\\$")


_TIME_RE = re.compile(r"(\d+(?:\s*[~\-]\s*\d+)?\s*(?:분|초|시간))")


def format_step(text: str) -> str:
    """조리 단계 문장을 마크다운으로 바꾼다. 불 조절에 중요한 시간("3분", "30초", "6~7분")을 굵게 보여준다."""
    return _TIME_RE.sub(r"**\1**", escape_md(text))


def header_html() -> str:
    return (
        '<div class="app-hero"><div class="logo" aria-hidden="true">🍳</div>'
        "<h1>냉장고를 부탁해</h1>"
        "<p>가진 재료로 오늘 저녁 메뉴를 정해드려요</p></div>"
    )


def note_html(kind: str, text: str) -> str:
    return f'<div class="note {kind}" role="status">{escape(text)}</div>'


def empty_state_html() -> str:
    return (
        '<div class="empty"><div class="big" aria-hidden="true">🥘</div>'
        "<p><b>오늘 뭐 먹지?</b><br>재료를 입력하고 추천 버튼을 눌러보세요.</p></div>"
    )


def _chips(items: list[str], kind: str, empty_text: str) -> str:
    if not items:
        return f'<span class="chip none">{escape(empty_text)}</span>'
    return "".join(f'<span class="chip {kind}">{escape(i)}</span>' for i in items)


def recipe_header_html(idx: int, r: dict) -> str:
    pct = round(r["match_rate"] * 100)
    level = "" if pct >= 70 else ("mid" if pct >= 40 else "low")
    servings = r.get("servings")
    servings_badge = f'<span class="badge">👥 {int(servings)}인분</span>' if servings else ""
    seasonings = r.get("seasonings") or []
    seasoning_row = (
        '<div class="ing-row"><span class="head">🧂 양념</span>'
        f'{_chips(seasonings, "season", "없음")}</div>'
        if seasonings else ""
    )
    return (
        f'<div class="recipe-title"><span class="no">{idx}.</span>{escape(r["name"])}</div>'
        '<div class="badges">'
        f'<span class="badge cuisine">{escape(r["cuisine"])}</span>'
        f'<span class="badge">⏱ {int(r["minutes"])}분</span>'
        f'<span class="badge">{escape(r["difficulty"])}</span>'
        f'{servings_badge}</div>'
        f'<p class="recipe-summary">{escape(r["summary"])}</p>'
        '<div class="match">'
        f'<div class="label"><span>재료 일치율</span><b>{pct}%</b></div>'
        f'<div class="track" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100" '
        f'aria-label="재료 일치율"><div class="fill {level}" style="width:{pct}%"></div></div></div>'
        '<div class="ing-row"><span class="head">✅ 보유</span>'
        f'{_chips(r["have_ingredients"], "have", "없음")}</div>'
        '<div class="ing-row"><span class="head">🛒 추가 필요</span>'
        f'{_chips(r["need_ingredients"], "need", "없음")}</div>'
        f"{seasoning_row}"
    )


def legal_html() -> str:
    return (
        '<div class="legal">※ 알레르기·건강 관련 정보는 참고용이며 의학적 조언이 아닙니다.<br>'
        "※ 메뉴를 평가하면 입력하신 재료·요청과 평가가 서비스 개선을 위해 익명으로 저장됩니다.</div>"
    )
