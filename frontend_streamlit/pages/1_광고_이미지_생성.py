# -*- coding: utf-8 -*-
import os
import requests
import streamlit as st
from dotenv import load_dotenv
import shutil
from pathlib import Path

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
.page { max-width: 1100px; margin: 0 auto; padding-bottom: 40px; }

/* hero */
.hero { text-align:center; padding: 18px 0 28px; }
.hero h1 { margin:0; font-size: clamp(26px, 4.4vw, 40px); font-weight:800;
           background:linear-gradient(90deg,#2563eb,#9333ea);
           -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.hero p { margin:8px 0 0; opacity:.85; font-size:15px; }

/* card */
.card { background: rgba(255,255,255,0.6); border:1px solid rgba(17,24,39,0.08);
        border-radius:16px; padding:24px; box-shadow:0 6px 18px rgba(0,0,0,0.08); }

/* button */
.stButton>button { 
    background:linear-gradient(90deg,#2563eb,#9333ea);
    color:#fff; font-weight:600; border-radius:12px; padding:10px 0;
    transition:all 0.2s ease;
}
.stButton>button:hover { 
    background:linear-gradient(90deg,#1d4ed8,#7e22ce);
    transform:translateY(-2px);
}

/* help 버튼 */
.stButton > button[kind="secondary"] {
  margin: 8px 0 14px 0;
  padding: 6px 14px;
  border-radius: 999px;
  font-weight: 800;
  color: #0f172a;
  background: 
    linear-gradient(#fff, #fff) padding-box,
    linear-gradient(90deg, #2563eb, #9333ea) border-box;
  border: 3px solid transparent;
  box-shadow: 0 6px 14px rgba(15,23,42,.08);
  transition: .15s;
}

.stButton > button[kind="secondary"]:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 20px rgba(15,23,42,.14);
}

/* help box */
.hint { font-size:14px; line-height:1.55; margin:10px 0;
        background:#fff8eb; border:1px solid #fcd34d;
        border-radius:12px; padding:14px 16px; box-shadow:0 4px 14px rgba(0,0,0,.08); }

/* result */
.result-img { border-radius:14px; box-shadow:0 10px 24px rgba(0,0,0,.15); }

/* archive btn */
.archive-btn {
  position:fixed; top:36px; right:32px;
  padding:12px 20px; border-radius:999px; line-height:1;
  background:#ffffff; color:#0f172a; font-weight:800;
  text-decoration:none; border:3px solid #F59E0B;
  box-shadow:0 8px 20px rgba(15,23,42,.10), inset 0 0 0 2px #fff;
  z-index:2147483647; transition:.15s;
}
.archive-btn:hover { transform:translateY(-2px);
  box-shadow:0 12px 28px rgba(15,23,42,.16), inset 0 0 0 2px #fff; }

/* 제거: 라벨 배경 박스 */
.stTextArea label, .stNumberInput label, .stTextInput label {
  background: transparent !important;
  padding: 0 !important;
}
</style>
<a class="archive-btn" href="/?page=4_%EB%82%B4%EA%B0%80_%EC%83%9D%EC%84%B1%ED%95%9C_%EC%9D%B4%EB%AF%B8%EC%A7%80">📂 보관함</a>
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
    <h1>광고 이미지 생성</h1>
    <p>문구를 입력하면 그에 맞는 이미지를 생성하고, 결과를 우측 상단 "📂보관함"에 저장합니다.</p>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ----------------------------
# Form UI
# ----------------------------
st.markdown('<div class="page"><div class="card">', unsafe_allow_html=True)

# 도움말 버튼
if st.button("💡 도움말 보기", key="help_img", use_container_width=False):
    st.session_state["show_help_img"] = not st.session_state.get("show_help_img", False)

if st.session_state.get("show_help_img", False):
    st.markdown(
        """
<div class="hint">
<b>무엇을 입력하면 좋을까?</b><br>
✔ 제품/서비스 이름<br>
✔ 혜택 (가격·할인·증정)<br>
✔ 기간/장소<br>
✔ CTA (예: 지금 주문/예약)<br><br>

<b>예시</b><br>
- “주말 한정 수제버거 세트 30% OFF, 오후 3~6시 해피아워, 지금 주문!”<br>
- “비건 초콜릿 케이크 런칭, 첫 구매 1+1 쿠폰 제공, 오늘만!”<br><br>

<b>팁</b><br>
- 원하는 분위기를 "🎨 스타일(선택)"란에 적어주세요.<br>
- 짧고 간결한 문장이 더 효과적입니다.
</div>
""",
        unsafe_allow_html=True,
    )

st.markdown("### ✍️ 광고 문구 입력", unsafe_allow_html=True)
text = st.text_area(
    label="",
    height=140,
    placeholder="예) 신메뉴 바질페스토 파스타 런칭! 2시~5시 타임세일, 오늘만 20% 할인",
    label_visibility="collapsed"
)

col1, col2 = st.columns(2)
with col1:
    style = st.text_input("🎨 스타일(선택)", placeholder="예) 빈티지, 미니멀, 네온, 시원함")
with col2:
    seed = st.number_input("🔢 seed(선택)", value=0, step=1, min_value=0)

generate = st.button("✨ 이미지 생성", use_container_width=True, type="primary")

st.markdown("</div></div>", unsafe_allow_html=True)

# ----------------------------
# Action
# ----------------------------
import shutil
from pathlib import Path

if generate:
    if not text.strip():
        st.warning("광고 문구를 입력해주세요.")
    else:
        payload = {
            "text": text.strip(),
            "style": style.strip() or None,
            "seed": int(seed) if seed else None
        }
        with st.spinner("이미지 생성 중..."):
            try:
                resp = requests.post(
                    f"{BACKEND}/generate/image-from-copy",
                    json=payload,
                    timeout=300
                )
                resp.raise_for_status()
            except Exception as e:
                st.error(f"백엔드 요청 실패: {e}")
            else:
                data = resp.json()
                file_url = data.get("file_url")

                if not file_url or not file_url.startswith("http"):
                    st.error(f"이미지 URL이 없습니다. 응답: {data}")
                else:
                    filename = Path(file_url).name

                    # ✅ 루트 절대경로 기준으로 설정
                    # frontend_streamlit/main.py → ../../data/outputs
                    ROOT_DIR = Path(__file__).resolve().parents[2]
                    root_output = ROOT_DIR / "data" / "outputs" / filename
                    backend_output = ROOT_DIR / "backend_fastapi" / "data" / "outputs" / filename

                    found_path = None

                    # 1️⃣ 루트 data/outputs 확인
                    if root_output.exists():
                        found_path = root_output
                        st.info(f"✅ 루트 data/outputs에서 발견: {found_path}")
                    # 2️⃣ backend_fastapi/data/outputs 확인 후 복사
                    elif backend_output.exists():
                        try:
                            (ROOT_DIR / "data" / "outputs").mkdir(parents=True, exist_ok=True)
                            shutil.copy2(backend_output, root_output)
                            found_path = root_output
                            st.info(f"📂 backend_fastapi/data/outputs에서 복사 → data/outputs/")
                        except Exception as e:
                            st.error(f"복사 중 오류 발생: {e}")
                    # 3️⃣ 둘 다 없음
                    else:
                        st.error(f"❌ 이미지 파일을 찾을 수 없습니다.\n검색 경로:\n{root_output}\n{backend_output}")

                    # 표시
                    if found_path and found_path.exists():
                        st.success("완료! 🎉 생성된 이미지를 확인하세요.")
                        st.image(str(found_path), use_container_width=True, caption="생성 결과")
                        st.code(str(found_path))


