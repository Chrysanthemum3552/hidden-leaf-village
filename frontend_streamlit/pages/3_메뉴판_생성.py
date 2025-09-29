# -*- coding: utf-8 -*-
import os, requests
import streamlit as st
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()
BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

st.title("🧾 메뉴판 생성")

# 가게명 / 테마 입력
shop = st.text_input("가게명", value="My Cafe")
theme = st.selectbox("테마", ["simple", "modern", "vintage", "neon", "korean"])

st.subheader("메뉴 입력")

# ⚠️ 'items'는 dict의 .items()와 충돌하므로 session_state에서는 'menu_items'로 사용
if "menu_items" not in st.session_state:
    st.session_state["menu_items"] = [
        {"name": "Americano", "price": 3000, "desc": "Hot/Iced"}
    ]

def render_items():
    for i, it in enumerate(st.session_state["menu_items"]):
        cols = st.columns([4, 2, 4, 1])
        it["name"] = cols[0].text_input("이름", value=it["name"], key=f"name_{i}")
        it["price"] = cols[1].number_input("가격", value=int(it["price"]), step=100, key=f"price_{i}")
        it["desc"] = cols[2].text_input("설명(선택)", value=it.get("desc", ""), key=f"desc_{i}")
        if cols[3].button("삭제", key=f"del_{i}"):
            st.session_state["menu_items"].pop(i)
            try:
                st.rerun()  # 최신 Streamlit
            except Exception:
                st.experimental_rerun()  # 구버전 호환

render_items()

# 메뉴 추가 버튼
if st.button("메뉴 추가"):
    st.session_state["menu_items"].append({"name": "New Item", "price": 0, "desc": ""})
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()

# 메뉴판 생성 버튼
if st.button("메뉴판 생성"):
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

            st.success("완료!")

            # 안전하게 키 접근
            img_url = data.get("file_url") or data.get("output_path")
            if img_url:
                st.image(img_url, caption="생성된 메뉴판")
                st.code(img_url)
            else:
                st.error(f"응답에 이미지 경로가 없습니다.\n{data}")

        except requests.RequestException as e:
            st.error(
                f"실패: {e}\n응답: {getattr(e, 'response', None) and getattr(e.response, 'text', '')}"
            )
