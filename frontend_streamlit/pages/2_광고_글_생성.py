import os
from typing import Optional, Dict, Any
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st
from dotenv import load_dotenv

# 1) 환경/상수
load_dotenv()

BACKEND: str = os.getenv("BACKEND_URL", "http://localhost:8000")
API_ENDPOINT: str = f"{BACKEND}/generate/copy-from-image"
REQ_TIMEOUT: int = 120

AGE_OPTIONS = ["", "10대", "20대", "30대", "40대", "시니어"]
ROLE_OPTIONS = ["", "학생", "직장인", "자영업", "육아", "프리미엄"]

# 2) 헬퍼 함수
def compose_persona(age: str, role: str) -> str:
    if age and role:
        return f"{age} {role}"
    return age or role or ""

def fetch_bytes(url: Optional[str], timeout: int = 10) -> Optional[bytes]:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception:
        try:
            alt = url.replace("localhost", "127.0.0.1")
            if alt != url:
                r2 = requests.get(alt, timeout=timeout)
                r2.raise_for_status()
                return r2.content
        except Exception:
            return None
    return None

def post_generate(files: Dict[str, Any], data: Dict[str, Any]) -> requests.Response:
    return requests.post(API_ENDPOINT, files=files, data=data, timeout=REQ_TIMEOUT)

# 3) 페이지 기본 설정
st.set_page_config(page_title="✍️ 광고 글 생성", page_icon="✍️", layout="wide")

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

/* main button */
.stButton>button { 
    background:linear-gradient(90deg,#2563eb,#9333ea);
    color:#fff; font-weight:600; border-radius:12px; padding:10px 0;
    transition:all 0.2s ease;
}
.stButton>button:hover { 
    background:linear-gradient(90deg,#1d4ed8,#7e22ce);
    transform:translateY(-2px);
}

/* help button */
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
.stTextArea label, .stNumberInput label, .stTextInput label,
.stSelectbox label, .stFileUploader label {
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
    <h1>광고 글 생성</h1>
    <p>이미지를 업로드하면 그에 맞는 광고 문구를 생성하고, 결과를 우측 상단 "📂보관함"에 저장합니다.</p>
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
if st.button("💡 도움말 보기", key="help_copy", use_container_width=False):
    st.session_state["show_help_copy"] = not st.session_state.get("show_help_copy", False)

if st.session_state.get("show_help_copy", False):
    st.markdown(
        """
<div class="hint">
<b>무엇을 업로드하면 좋을까?</b><br>
✔ 제품 사진, 로고 이미지, 포스터 초안<br>
✔ 홍보하고 싶은 매장/브랜드 이미지<br><br>

<b>예시</b><br>
- 카페 신메뉴 사진을 올리면 → 카피 문구 자동 생성<br>
- 브랜드 로고 이미지를 올리면 → 광고 문구 추천<br><br>

<b>팁</b><br>
- 연령/역할 옵션을 선택하면 톤이 달라집니다.<br>
- 핵심 키워드를 입력하면 더 정밀하게 조정됩니다.
</div>
""",
        unsafe_allow_html=True,
    )

# 입력 폼
img = st.file_uploader("이미지를 업로드하세요", type=["png", "jpg", "jpeg", "webp"])

col1, col2 = st.columns(2)
with col1:
    age = st.selectbox("연령(선택)", AGE_OPTIONS, index=0)
with col2:
    role = st.selectbox("역할/상황(선택)", ROLE_OPTIONS, index=0)

if "kw_input" not in st.session_state:
    st.session_state.kw_input = ""

st.text_input(
    "핵심 키워드 (선택, 쉼표)",
    key="kw_input",
    placeholder="예: 가성비, 빠른배송, 감성, 프리미엄, 친환경, 선물추천...",
)

must_include_kw = st.checkbox("핵심 키워드 최소 1개 반드시 포함", value=False)
business_name = st.text_input("상호/브랜드명 (선택)", placeholder="예: 나뭇잎마을")
must_include_brand = st.checkbox("상호/브랜드명을 반드시 포함", value=False)

generate = st.button("✨ 광고 글 생성", use_container_width=True, type="primary")

st.markdown("</div></div>", unsafe_allow_html=True)

# ----------------------------
# Action
# ----------------------------
if generate:
    if not img:
        st.warning("이미지를 선택하세요.")
    else:
        with st.spinner("생성 중..."):
            files = {"file": (img.name, img.getvalue(), img.type)}
            persona_val = compose_persona(age, role)
            payload = {
                "persona": persona_val or None,
                "user_keywords_csv": (st.session_state.get("kw_input") or None),
                "must_include_keywords": str(bool(must_include_kw)).lower(),
                "business_name": business_name or None,
                "must_include_brand": str(bool(must_include_brand)).lower(),
            }
            data = {k: v for k, v in payload.items() if v not in ("", None)}

            try:
                resp = post_generate(files, data)
            except Exception as e:
                st.error(f"요청 오류: {e}")
            else:
                if not resp.ok:
                    st.error(f"실패: {resp.text}")
                else:
                    res = resp.json()
                    st.success("완료! 🎉 생성된 광고 문구를 확인하세요.")

                    img_url = res.get("uploaded_url")
                    img_path = res.get("uploaded_path")
                    content = fetch_bytes(img_url) if img_url else None

                    if content:
                        st.image(content, caption="업로드 이미지", use_container_width=True)
                    elif img_path and os.path.exists(img_path):
                        st.image(img_path, caption="업로드 이미지(로컬)", use_container_width=True)

                    st.subheader("생성된 광고 문구")
                    st.write(res.get("copy", ""))

                    structured = res.get("structured") or {}
                    if structured:
                        st.caption("헤드라인 / 서브라인 / 해시태그")
                        st.write(f"**{structured.get('headline','')}**")
                        st.write(structured.get('subline',''))
                        tags = " ".join(structured.get('hashtags', []))
                        if tags:
                            st.write(tags)

                    st.caption(f"log: {res.get('log_url') or res.get('log_path')}")
                    with st.expander("응답 원본(JSON) 보기"):
                        st.json(res)
