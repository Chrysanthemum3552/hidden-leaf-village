import streamlit as st

st.set_page_config(page_title="Ad Gen Service", page_icon="🎯", layout="centered")

st.title("Ad Gen Service")
st.write("원하는 작업을 선택하세요.")

col1, col2, col3 = st.columns(3)
with col1:
    st.page_link("pages/1_광고_이미지_생성.py", label="🖼️ 광고 이미지 생성", icon="➡️")
with col2:
    st.page_link("pages/2_광고_글_생성.py", label="✍️ 광고 글 생성", icon="➡️")
with col3:
    st.page_link("pages/3_메뉴판_생성.py", label="🧾 메뉴판 생성", icon="➡️")
