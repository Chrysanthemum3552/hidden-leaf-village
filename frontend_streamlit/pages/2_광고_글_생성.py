import os, requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

st.title("✍️ 광고 글 생성 (이미지→글)")
img = st.file_uploader("이미지 업로드", type=["png","jpg","jpeg","webp"])

if st.button("광고 글 생성"):
    if not img:
        st.warning("이미지를 선택하세요.")
    else:
        with st.spinner("생성 중..."):
            files = {"file": (img.name, img.getvalue(), img.type)}
            r = requests.post(f"{BACKEND}/generate/copy-from-image", files=files, timeout=120)
            if r.ok:
                data = r.json()
                st.success("완료!")
                st.image(data["uploaded_path"], caption="업로드 원본")
                st.subheader("생성된 광고 문구")
                st.write(data["copy"])
                st.caption(f"log: {data['log_path']}")
            else:
                st.error(f"실패: {r.text}")
