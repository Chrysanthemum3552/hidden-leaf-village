import streamlit as st
from pathlib import Path
from PIL import Image
import base64

st.set_page_config(page_title="내가 생성한 이미지", layout="wide", initial_sidebar_state="collapsed")

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

/* ===== 버튼 전역 스타일 (Streamlit 위젯 DOM 분리 대응) ===== */
.stDownloadButton>button, .stButton>button{
  width:100% !important;
  display:flex !important; align-items:center !important; justify-content:center !important;
  border-radius:12px !important;
  padding:14px 12px !important;
  font-size:13.5px !important; font-weight:700 !important;
  border:1px solid transparent !important;
  box-shadow:0 2px 8px rgba(0,0,0,0.06) !important;
}

/* 다운로드 = 연한 녹색 */
.stDownloadButton>button{
  background:#e9f9ef !important;        /* very light green */
  color:#0f5132 !important;
  border-color:#b7eb8f !important;
}

/* 삭제 = 연한 적색 */
.stButton>button{
  background:#fdecec !important;         /* very light red */
  color:#7f1d1d !important;
  border-color:#f8b4b4 !important;
}

/* 카드와 버튼 사이 간격 */
.btn-gap{ height:10px; }
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
    # 이미지 최신순
    img_files = sorted(
        [f for f in OUTPUT_DIR.iterdir() if f.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

    if not img_files:
        st.info("이미지가 없습니다.")
    else:
        # 조금 더 크게 보이도록 3열
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

                    # 정사각형 카드 + 이미지
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

                    # 액션 바: 이미지 바로 아래 1:1 가로 분할
                    st.markdown('<div class="actions">', unsafe_allow_html=True)
                    c1, c2 = st.columns(2, gap="small")
                    with c1:
                        st.download_button("⬇ 다운로드", data=img_bytes, file_name=img_path.name, mime=mime, key=f"dl_{i}")
                    with c2:
                        if st.button("🗑 삭제", key=f"del_{i}"):
                            try:
                                img_path.unlink()
                                st.experimental_rerun()
                            except Exception as e:
                                st.error(f"삭제 실패: {e}")
                    st.markdown('</div>', unsafe_allow_html=True)

                except Exception as e:
                    st.error(f"{img_path.name} 불러오기 실패: {e}")

                st.markdown('</div>', unsafe_allow_html=True)
