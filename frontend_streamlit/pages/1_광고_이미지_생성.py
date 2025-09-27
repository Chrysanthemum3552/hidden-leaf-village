import os, requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

st.title("🖼️ 광고 이미지 생성 (글→이미지)")
text = st.text_area("광고 문구를 입력하세요")
style = st.text_input("스타일(선택): 예) vintage, minimal, neon")
seed = st.number_input("seed(선택)", value=0, step=1)

if st.button("이미지 생성"):
    with st.spinner("생성 중..."):
        r = requests.post(f"{BACKEND}/generate/image-from-copy",
                          json={"text": text, "style": style or None, "seed": seed or None}, timeout=300)
        if r.ok:
            data = r.json()
            st.success("완료!")
            st.image(data["output_path"])
            st.code(data["output_path"])
        else:
            st.error(f"실패: {r.text}")
