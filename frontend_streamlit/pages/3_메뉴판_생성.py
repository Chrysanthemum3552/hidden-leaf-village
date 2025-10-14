# -*- coding: utf-8 -*-
import os, requests, shutil
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

# ----------------------------
# 환경 변수 로드
# ----------------------------
load_dotenv()
BACKEND = (
    os.getenv("BACKEND_URL")
    or os.getenv("BACKEND_PUBLIC_URL")
    or "https://hidden-leaf-village.onrender.com"
).rstrip("/")

# ----------------------------
# 페이지 기본 설정
# ----------------------------
st.set_page_config(page_title="🧾 메뉴판 생성", page_icon="🧾", layout="wide")

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
    <h1>메뉴판 생성</h1>
    <p>가게명과 메뉴를 입력하면 테마에 맞는 메뉴판 이미지를 자동 생성하고, 결과를 우측 상단 "📂보관함"에 저장합니다.</p>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ----------------------------
# Form UI
# ----------------------------
st.markdown('<div class="page"><div class="card">', unsafe_allow_html=True)

if "show_help_menu" not in st.session_state:
    st.session_state["show_help_menu"] = False

if st.button("💡 도움말 보기", key="help_menu", use_container_width=False):
    st.session_state["show_help_menu"] = not st.session_state["show_help_menu"]

if st.session_state["show_help_menu"]:
    st.markdown(
        """
<div class="hint">
<b>무엇을 입력하면 좋을까?</b><br>
✔ 가게 이름 / 테마 선택<br>
✔ 메뉴명과 가격, 짧은 설명<br><br>

<b>예시</b><br>
- 아메리카노 3000원 (Hot/Iced)<br>
- 카페라떼 5000원 (우유 + 에스프레소)<br>
- 바닐라 라떼 5500원 (달콤한 바닐라 향)<br><br>

<b>팁</b><br>
- 테마를 선택하면 스타일이 달라집니다.<br>
- 메뉴 수가 많아도 자동으로 정리됩니다.
</div>
""",
        unsafe_allow_html=True,
    )

shop = st.text_input("가게명", value="My Cafe")
theme = st.selectbox("테마", ["simple", "modern", "vintage", "neon", "korean"])

st.subheader("메뉴 입력")

if "menu_items" not in st.session_state:
    st.session_state["menu_items"] = [{"name": "Americano", "price": 3000, "desc": "Hot/Iced"}]

def render_items():
    idxs = list(range(len(st.session_state["menu_items"])))
    for i in idxs:
        it = st.session_state["menu_items"][i]
        cols = st.columns([4, 2, 4, 1])
        it["name"] = cols[0].text_input("이름", value=it.get("name", ""), key=f"name_{i}")
        it["price"] = cols[1].number_input("가격", value=int(it.get("price", 0)), step=100, key=f"price_{i}")
        it["desc"] = cols[2].text_input("설명(선택)", value=it.get("desc", ""), key=f"desc_{i}")
        if cols[3].button("삭제", key=f"del_{i}"):
            st.session_state["menu_items"].pop(i)
            st.rerun()

render_items()

if st.button("➕ 메뉴 추가", use_container_width=True, type="secondary"):
    st.session_state["menu_items"].append({"name": "", "price": 0, "desc": ""})
    st.rerun()

generate = st.button("✨ 메뉴판 생성", use_container_width=True, type="primary")

st.markdown("</div></div>", unsafe_allow_html=True)

# ----------------------------
# Action
# ----------------------------
if generate:
    payload = {
        "shop_name": shop or None,
        "theme": theme,
        "items": st.session_state["menu_items"],
    }
    with st.spinner("생성 중..."):
        try:
            r = requests.post(f"{BACKEND}/generate/menu-board", json=payload, timeout=120)
            r.raise_for_status()
            data = r.json()

            st.success("완료! 🎉 생성된 메뉴판을 확인하세요.")

            img_url = data.get("image_url") or data.get("url") or data.get("file_url")
            if not img_url:
                path = data.get("path")
                if path:
                    img_url = path if path.startswith("http") else f"{BACKEND}{path if path.startswith('/') else '/' + path}"

            if not img_url:
                st.error(f"응답에 올바른 이미지 URL이 없습니다.\n{data}")
            else:
                filename = Path(img_url).name

                # ✅ 루트 기준 탐색 & 복사 로직
                ROOT_DIR = Path(__file__).resolve().parents[2]
                root_output = ROOT_DIR / "data" / "outputs" / filename
                backend_output = ROOT_DIR / "backend_fastapi" / "data" / "outputs" / filename
                found_path = None

                if root_output.exists():
                    found_path = root_output
                    st.info(f"✅ data/outputs에서 이미지 확인됨")
                elif backend_output.exists():
                    try:
                        (ROOT_DIR / "data" / "outputs").mkdir(parents=True, exist_ok=True)
                        shutil.copy2(backend_output, root_output)
                        found_path = root_output
                        st.info("📂 backend_fastapi/data/outputs에서 복사 완료 → data/outputs/")
                    except Exception as e:
                        st.error(f"복사 중 오류 발생: {e}")
                else:
                    st.error(f"❌ 이미지 파일을 찾을 수 없습니다.\n{root_output}\n{backend_output}")

                if found_path and found_path.exists():
                    st.image(str(found_path), caption="생성된 메뉴판", use_container_width=True)
                    st.code(str(found_path))

        except requests.RequestException as e:
            resp_text = ""
            if getattr(e, "response", None) is not None:
                try:
                    resp_text = e.response.text
                except Exception:
                    resp_text = str(e)
            st.error(f"실패: {e}\n응답: {resp_text}")
