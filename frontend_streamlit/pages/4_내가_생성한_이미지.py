import streamlit as st
from pathlib import Path
import base64

st.set_page_config(
    page_title="내가 생성한 이미지",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 스타일 ---
st.markdown("""
<style>
.page-title{
  display:flex; align-items:center; gap:10px; margin-bottom:12px;
}
.page-title span{ font-size:28px; font-weight:800; letter-spacing:-.3px; }

/* 카드 */
.gallery-col{ margin-bottom:28px; }
.card{
  width:100%;
  border-radius:18px;
  overflow:hidden;
  background:rgba(255,255,255,0.06);
  border:1px solid rgba(255,255,255,0.14);
  box-shadow:0 10px 26px rgba(0,0,0,0.28);
  transition:transform .18s ease, box-shadow .18s ease;
}
.card:hover{ transform:translateY(-4px); box-shadow:0 16px 36px rgba(0,0,0,0.34); }

/* 정사각형 미디어 */
.card .media{ width:100%; aspect-ratio:1/1; overflow:hidden; }
.card .media img{ width:100%; height:100%; object-fit:cover; display:block; }

/* 버튼 영역(시각적 여백) */
.actions{ height:10px; }

/* Streamlit 위젯을 원래 디자인처럼 보이게 커스텀 */
div[data-testid="stDownloadButton"],
div[data-testid="stButton"]{
  width:100%;
}
div[data-testid="stDownloadButton"] > button,
div[data-testid="stButton"] > button{
  width:100%;
  border-radius:12px;
  padding:12px 0;
  font-size:13.5px;
  font-weight:700;
  border:1px solid transparent;
  box-shadow:0 2px 8px rgba(0,0,0,0.06);
  white-space:nowrap;
  min-width:0;
}

/* 다운로드 버튼(초록) */
div[data-testid="stDownloadButton"] > button{
  background:#e9f9ef;
  color:#0f5132;
  border-color:#b7eb8f;
}

/* 삭제 버튼(빨강) */
div[data-testid="stButton"] > button{
  background:#fdecec;
  color:#7f1d1d;
  border-color:#f8b4b4;
}

/* hover 효과 약간 추가(옵션) */
div[data-testid="stDownloadButton"] > button:hover{
  filter:brightness(0.98);
}
div[data-testid="stButton"] > button:hover{
  filter:brightness(0.98);
}
</style>
""", unsafe_allow_html=True)

# --- 제목 ---
st.markdown('<div class="page-title">📁 <span>내가 생성한 이미지</span></div>', unsafe_allow_html=True)

# --- 경로 (프로젝트 루트의 data/outputs) ---
ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT_DIR / "data" / "outputs"

if not OUTPUT_DIR.exists():
    st.warning(f"폴더가 없습니다: {OUTPUT_DIR}")
else:
    img_files = sorted(
        [f for f in OUTPUT_DIR.iterdir() if f.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

    if not img_files:
        st.info("이미지가 없습니다.")
    else:
        NUM_COLS = 4
        cols = st.columns(NUM_COLS, gap="large")

        for i, img_path in enumerate(img_files):
            with cols[i % NUM_COLS]:
                st.markdown('<div class="gallery-col">', unsafe_allow_html=True)

                try:
                    with open(img_path, "rb") as f:
                        img_bytes = f.read()
                        mime = f"image/{img_path.suffix.lower().strip('.')}"
                        b64 = base64.b64encode(img_bytes).decode()

                    # 카드 (이미지)
                    st.markdown(
                        f'''
                        <div class="card">
                          <div class="media">
                            <img src="data:{mime};base64,{b64}" alt="preview">
                          </div>
                        </div>
                        ''',
                        unsafe_allow_html=True
                    )

                    # 버튼 행 여백(원래 .actions 역할)
                    st.markdown('<div class="actions"></div>', unsafe_allow_html=True)

                    # 버튼 2개를 같은 행처럼 보이도록 columns 사용
                    dl_col, del_col = st.columns(2, gap="small")

                    with dl_col:
                        st.download_button(
                            "⬇ 다운로드",
                            data=img_bytes,
                            file_name=img_path.name,
                            mime=mime,
                            key=f"download_{i}",
                            use_container_width=True
                        )

                    with del_col:
                        if st.button("🗑 삭제", key=f"delete_{i}", use_container_width=True):
                            try:
                                img_path.unlink()  # 파일 삭제
                                st.success(f"{img_path.name} 삭제됨")
                                try:
                                    st.rerun()
                                except Exception:
                                    st.experimental_rerun()
                            except Exception as e:
                                st.error(f"삭제 실패: {e}")

                except Exception as e:
                    st.error(f"{img_path.name} 불러오기 실패: {e}")

                st.markdown('</div>', unsafe_allow_html=True)
