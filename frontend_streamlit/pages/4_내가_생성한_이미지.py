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

/* 버튼 영역 */
.actions { width:100%; margin-top:10px; }
.btn-row {
  display:flex;
  gap:8px;              /* 버튼 사이 간격 */
  width:100%;
}
.btn-row a,
.btn-row button {
  flex:1;               /* 동일한 비율 */
  text-align:center;
  border-radius:12px;
  padding:12px 0;
  font-size:13.5px;
  font-weight:700;
  border:1px solid transparent;
  cursor:pointer;
  box-shadow:0 2px 8px rgba(0,0,0,0.06);
  white-space:nowrap;   /* 줄바꿈 방지 */
  min-width:0;          /* flex-shrink 허용 */
}

/* 다운로드 버튼 */
.btn-row .download {
  background:#e9f9ef;
  color:#0f5132;
  border-color:#b7eb8f;
  text-decoration:none; /* 링크 밑줄 제거 */
  display:flex;
  align-items:center;
  justify-content:center;
}

/* 삭제 버튼 */
.btn-row .delete {
  background:#fdecec;
  color:#7f1d1d;
  border-color:#f8b4b4;
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

                    # 버튼 행 (다운로드 / 삭제)
                    st.markdown(
                        f"""
                        <div class="actions">
                          <div class="btn-row">
                            <a href="data:{mime};base64,{b64}" 
                               download="{img_path.name}" 
                               class="download">⬇ 다운로드</a>
                            <button class="delete" onclick="fetch('/delete/{i}')">🗑 삭제</button>
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                except Exception as e:
                    st.error(f"{img_path.name} 불러오기 실패: {e}")

                st.markdown('</div>', unsafe_allow_html=True)
