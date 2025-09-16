import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st
from dotenv import load_dotenv

# ----------------------------
# Env & Page Config
# ----------------------------
load_dotenv()
BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="🖼️ 광고 이미지 생성", page_icon="🖼️", layout="wide")

# ----------------------------
# Styles
# ----------------------------
st.markdown(
    """
<style>
.page { max-width: 1100px; margin: 0 auto; }
.hero { text-align:center; padding: 8px 0 12px; }
.hero h1 { margin: 0; font-size: clamp(24px, 4.2vw, 34px); letter-spacing: -0.02em; }
.hero p { margin: 6px 0 0; opacity:.85; }

.card { background: rgba(17,24,39,0.03); border: 1px solid rgba(17,24,39,0.08);
        border-radius: 14px; padding: 18px; }
.hint { font-size: 13px; line-height: 1.55; opacity: .9; margin: 6px 0 0; }

hr.sep { border: none; height: 1px; background: rgba(17,24,39,.08); margin: 12px 0 16px; }

.result-img { border-radius: 12px; box-shadow: 0 8px 22px rgba(0,0,0,.12); }

.small { font-size: 12.5px; opacity: .85; }
</style>
""",
    unsafe_allow_html=True,
)

# ----------------------------
# Header
# ----------------------------
st.markdown(
    """
<div class="page">
  <div class="hero">
    <h1>🖼️ 광고 이미지 생성 (글 → 이미지)</h1>
    <p>문구를 입력하면 백엔드가 이미지를 생성하고, 결과를 <b>data/outputs</b>에도 저장합니다.</p>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ----------------------------
# Helpers
# ----------------------------
def guess_public_url(output_path: str) -> str:
    """
    백엔드가 반환한 output_path가
    - http(s)://...  → 그대로 사용
    - /static/...     → BACKEND + 해당 경로
    - 로컬파일 경로   → 파일명만 추출해 BACKEND/static/outputs/<name> 으로 가정
    """
    if not output_path:
        return ""
    p = output_path.strip()
    if p.startswith("http://") or p.startswith("https://"):
        return p
    if "/static/" in p:
        tail = p.split("/static/", 1)[-1]
        return f"{BACKEND}/static/{tail.lstrip('/')}"
    name = os.path.basename(p)
    return f"{BACKEND}/static/outputs/{name}"

def save_to_frontend_outputs(public_url: str) -> Path:
    """
    public_url에서 이미지를 GET하여 프로젝트 루트의 data/outputs 에 저장.
    현재 파일이 pages/ 아래에 있다고 가정하여 상위 2단계를 프로젝트 루트로 사용.
    """
    # pages/xxx.py -> frontend_streamlit/pages -> 프로젝트 루트의 상위 2단계
    project_root = Path(__file__).resolve().parents[2]
    out_dir = project_root / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(public_url)
    name = os.path.basename(parsed.path) or f"gen_{uuid.uuid4().hex}.png"
    if "." not in name:
        name += ".png"

    save_path = out_dir / name
    resp = requests.get(public_url, timeout=120)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        f.write(resp.content)
    return save_path

# ----------------------------
# Form UI
# ----------------------------
st.markdown('<div class="page">', unsafe_allow_html=True)
st.markdown('<div class="card">', unsafe_allow_html=True)

show_help = st.checkbox("설명 보기", value=False)

text = st.text_area(
    "광고 문구를 입력하세요",
    height=140,
    placeholder="예) 신메뉴 바질페스토 파스타 런칭! 2시~5시 타임세일, 오늘만 20% 할인",
)
if show_help:
    st.markdown(
        """
<div class="hint">
<strong>어떻게 쓰면 좋을까?</strong><br>
- 핵심: 제품/서비스, 혜택(가격·할인·증정), 기간/장소, CTA(예: 지금 주문/예약)<br>
- 톤: 친근·프리미엄·미니멀 등 원하는 분위기를 명시하면 좋아요.<br>
- 예시:<br>
&nbsp;&nbsp;• <i>“주말 한정 수제버거 세트 30% OFF, 오후 3~6시 해피아워, 지금 주문!”</i><br>
&nbsp;&nbsp;• <i>“비건 초콜릿 케이크 런칭, 첫 구매 1+1 쿠폰 제공, 오늘만!”</i>
</div>
""",
        unsafe_allow_html=True,
    )

col1, col2 = st.columns(2)
with col1:
    style = st.text_input("스타일(선택)", placeholder="예) vintage, minimal, neon")
    if show_help:
        st.markdown(
            """
<div class="hint">
- 쉼표로 여러 스타일 지정 가능 (예: <i>“vintage, minimal, film grain”</i>)<br>
- 키워드 예: minimal, neon, retro, vintage, poster, photo-realistic, 3D, Korean poster 등
</div>
""",
            unsafe_allow_html=True,
        )
with col2:
    seed = st.number_input("seed(선택)", value=0, step=1, min_value=0)
    if show_help:
        st.markdown(
            """
<div class="hint">
- 같은 입력으로 동일한 결과를 원하면 <b>seed</b>를 고정하세요.<br>
- <i>0</i>은 무작위 취급(아래 요청에서 <code>None</code>으로 변환).
</div>
""",
            unsafe_allow_html=True,
        )

st.markdown('<hr class="sep"/>', unsafe_allow_html=True)
generate = st.button("✨ 이미지 생성", use_container_width=True, type="primary")

st.markdown("</div>", unsafe_allow_html=True)  # .card
st.markdown("</div>", unsafe_allow_html=True)  # .page

# ----------------------------
# Action
# ----------------------------
if generate:
    if not text.strip():
        st.warning("광고 문구를 입력해주세요.")
    else:
        payload = {
            "text": text.strip(),
            "style": (style.strip() or None),
            "seed": (int(seed) if int(seed) != 0 else None),
        }
        with st.spinner("이미지 생성 중..."):
            try:
                resp = requests.post(
                    f"{BACKEND}/generate/image-from-copy",
                    json=payload,
                    timeout=120,
                )
            except Exception as e:
                st.error(f"백엔드 요청 실패: {e}")
            else:
                if not resp.ok:
                    st.error(f"실패: {resp.status_code} - {resp.text}")
                else:
                    data = {}
                    try:
                        data = resp.json()
                    except Exception:
                        st.error("응답 파싱 실패(JSON 아님)")
                        st.stop()

                    # 백엔드가 반환한 경로 추출
                    output_path = data.get("output_path") or data.get("path") or ""
                    public_url = guess_public_url(output_path)
                    if not public_url:
                        st.error("백엔드 응답에서 이미지 경로를 확인할 수 없습니다.")
                        st.stop()

                    # 결과 표시
                    st.success("완료! 아래 이미지를 확인하세요.")
                    st.image(public_url, use_column_width=True, caption="생성 결과")

                    # data/outputs 에 저장
                    try:
                        saved_path = save_to_frontend_outputs(public_url)
                        st.info("프론트엔드 저장 경로")
                        st.code(str(saved_path), language="text")
                        st.caption(
                            "※ 프로젝트 루트 기준: data/outputs/ 에 복사 저장되었습니다."
                        )
                    except Exception as e:
                        st.warning(f"로컬 저장 실패(무시 가능): {e}")
