import streamlit as st
from urllib.parse import quote
from pathlib import Path
import html, os

st.set_page_config(page_title="광고 생성 도우미", layout="wide", initial_sidebar_state="collapsed")

# --- 쿼리 → switch_page 라우팅 ---
q = st.query_params
page_key = q.get("page")
if page_key:
    st.switch_page(f"pages/{page_key}.py")

# --- 데이터 ---
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")

PAGES = [
    {
        "badge": "🖼️ IMAGE",
        "thumb": f"{BACKEND_PUBLIC_URL}/static/images/1.png",
        "title": "광고 이미지 생성",
        "desc": "문구만 입력하면 스타일에 맞는 광고 이미지를 자동 생성합니다."
    },
    {
        "badge": "✍️ COPY",
        "thumb": f"{BACKEND_PUBLIC_URL}/static/images/2.png",
        "title": "광고 글 생성",
        "desc": "이미지/키워드 기반으로 그에 딱 맞는 광고글을 생성합니다."
    },
    {
        "badge": "🧾 MENU",
        "thumb": f"{BACKEND_PUBLIC_URL}/static/images/3.png",
        "title": "메뉴판 생성",
        "desc": "메뉴와 가격을 입력하면 그에 맞는 메뉴판을 만듭니다."
    },
]

EXAMPLE_FILES = [f"example_{i}.png" for i in range(1, 9)]
SAMPLES = [
    (f"{BACKEND_PUBLIC_URL}/static/outputs/{fname}", f"Example {i}")
    for i, fname in enumerate(EXAMPLE_FILES, start=1)
]
ROUTES = {
    "광고 이미지 생성": "1_광고_이미지_생성",
    "광고 글 생성":   "2_광고_글_생성",
    "메뉴판 생성":     "3_메뉴판_생성",
}

def build_cards_html():
    items = []
    for c in PAGES:
        key = ROUTES[c["title"]]
        href = f"/?page={quote(key)}"
        items.append(f"""
<a class="card" href="{href}">
  <div class="card-thumb" style="background-image:url('{c["thumb"]}');">
  </div>
  <div class="card-body">
    <div class="card-desc">{html.escape(c["desc"])} </div>
  </div>
</a>
""")
    return "".join(items)

def build_templates_html() -> str:
    cards = []
    for url, cap in SAMPLES:
        cap_esc = html.escape(cap, quote=True)
        cards.append(f"""
<div class="template">
  <img src="{url}" alt="{cap_esc}" loading="lazy" decoding="async">
</div>
""".strip())
    return "\n".join(cards)

# --- CSS ---
CSS = """
<style>
html, body {
  margin: 0; padding: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', Arial, 'Helvetica Neue', sans-serif;
  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
  background: transparent;
}
.main-block { max-width: 1200px; margin: 0 auto; }
.stApp, .stApp > header, .stApp > div, .block-container {
  background: transparent !important;
}

/* 배경 */
.aurora-bg { 
  position: fixed; inset: 0; z-index: -2; background: linear-gradient(180deg, #1a237e 0%, #0d1333 100%);
}
.aurora-layer {
  position: fixed; inset: -10% -10% 0 -10%; z-index: -1; pointer-events: none;
  background:
    radial-gradient(1200px 300px at 20% 20%, rgba(91,108,255,0.35), transparent 60%),
    radial-gradient(1000px 280px at 70% 35%, rgba(147,51,234,0.25), transparent 60%),
    radial-gradient(900px 240px at 40% 70%, rgba(56,189,248,0.22), transparent 60%),
    radial-gradient(1200px 320px at 85% 80%, rgba(99,102,241,0.28), transparent 60%);
  filter: blur(14px) saturate(110%);
  animation: auroraMove 22s ease-in-out infinite alternate;
}
@keyframes auroraMove {
  0%   { transform: translateY(-2%) scale(1); }
  50%  { transform: translateY(-5%) scale(1.03); }
  100% { transform: translateY(-2%) scale(1); }
}
@keyframes fadeUp {
  0% { opacity: 0; transform: translateY(20px); }
  100% { opacity: 1; transform: translateY(0); }
}

/* 별 */
.stars:before {
  content:""; position: fixed; inset:0; z-index:-1; pointer-events:none;
  background-image:
    radial-gradient(2px 2px at 20% 30%, rgba(255,255,255,0.6), transparent 60%),
    radial-gradient(1.5px 1.5px at 70% 20%, rgba(255,255,255,0.45), transparent 60%),
    radial-gradient(1.8px 1.8px at 35% 70%, rgba(255,255,255,0.5), transparent 60%),
    radial-gradient(1.3px 1.3px at 85% 60%, rgba(255,255,255,0.35), transparent 60%);
  opacity:.45;
}

/* Hero */
.hero { padding: 68px 0 28px; text-align: center; color: #fff;
  animation: fadeUp 1s ease both; animation-delay: 0s; }
.hero h1 {
  font-family: 'Montserrat', 'Raleway', 'Pretendard Variable', sans-serif;
  font-size: clamp(36px, 5vw, 56px);
  font-weight: 900;
  margin: 0;
  letter-spacing: -0.01em;
  background: linear-gradient(90deg, #60A5FA, #A78BFA, #34D399);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  text-shadow: 0 0 14px rgba(100, 180, 255, 0.5);
}
.hero p {
  font-family: 'Raleway', 'Pretendard Variable', 'Inter', sans-serif;
  font-size: clamp(14px, 1.8vw, 20px);
  font-weight: 400;
  margin-top: 14px;
  letter-spacing: 0.5px;
  color: rgba(229, 231, 235, 0.9);
  text-shadow: 0 0 6px rgba(50, 120, 200, 0.4);
}

/* Section titles */
.section-title {
  font-family: 'Raleway', 'Pretendard Variable', sans-serif;
  font-size: clamp(18px, 2vw, 26px);
  font-weight: 700;
  text-align: center;
  margin: 40px 0 20px;
  letter-spacing: 1px;
  color: #E0E7FF;
  position: relative;
}
.section-start { animation: fadeUp 1s ease both; animation-delay: 0.5s; }
.section-templates { animation: fadeUp 1s ease both; animation-delay: 1s; }
.section-title::after {
  content: "";
  display: block;
  width: 80px;
  height: 3px;
  margin: 10px auto 0;
  border-radius: 2px;
  background: linear-gradient(90deg, #60A5FA, #A78BFA, #34D399);
}

/* 카드 */
.card-row {
  display: flex; gap: 18px; justify-content: center; flex-wrap: wrap;
  padding: 8px 4px 4px;
}
.card {
  display: block;
  text-decoration: none;
  color: inherit;
  width: 340px;
  border-radius: 20px;
  overflow: hidden;
  position: relative;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.18);
  box-shadow: 0 12px 28px rgba(0,0,0,0.25);
  transition: transform .25s ease, box-shadow .25s ease, filter .25s ease;
}
.card:hover {
  transform: translateY(-6px) scale(1.02);
  box-shadow: 0 20px 48px rgba(0,0,0,0.35), 0 0 16px rgba(120,180,255,0.35);
  filter: brightness(1.08);
}

.card-thumb { height: 160px; width: 100%; background-size: cover; background-position: center; }
.card-badge { position:absolute; top:10px; left:10px; background: rgba(0,0,0,.35); padding:6px 10px; border-radius:999px; font-weight:700; font-size:12px; }
.card-body { padding: 16px 18px 18px; }
.card-title {
  font-size: 18px;
  font-weight: 800;
  text-align: center;
  margin-bottom: 8px;
  color: #FACC15;
  text-shadow: 0 1px 3px rgba(0,0,0,0.45);
}
.card-desc {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
  color: #E5E9FF;
  opacity: 0.95;
  text-shadow: 0 1px 2px rgba(0,0,0,0.4);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Templates */
.template {
  flex: 0 0 auto;
  width: 220px;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.18);
  background: rgba(255,255,255,.06);
  box-shadow: 0 10px 24px rgba(0,0,0,.18);
  transition: transform .25s ease, box-shadow .25s ease;
}
.template:hover {
  transform: translateY(-4px) scale(1.05);
  box-shadow: 0 16px 36px rgba(0,0,0,.28), 0 0 14px rgba(120,180,255,0.35);
}
.template-marquee { position: relative; overflow: hidden; padding: 8px 0 12px; }
.marquee-track { display: flex; gap: 14px; will-change: transform; width: max-content; animation: marqueeRight 40s linear infinite; }
.template-marquee:hover .marquee-track { animation-play-state: paused; }
@media (prefers-reduced-motion: reduce) { .marquee-track { animation: none; } }
.template { flex:0 0 auto; width: 220px; border-radius:14px; overflow:hidden;
  border:1px solid rgba(255,255,255,.18); background: rgba(255,255,255,.06);
  box-shadow: 0 10px 24px rgba(0,0,0,.18); }
.template img { display:block; width:100%; height:auto; }
.template .cap { padding:8px 10px; font-size:12px; color:#fff; opacity:.9; }
@keyframes marqueeRight { 0% { transform: translateX(-50%); } 100% { transform: translateX(0%); } }

/* Footer */
.footer {
  margin: 40px auto;
  padding: 18px 24px;
  max-width: 500px;
  text-align: center;
  font-family: 'Pretendard Variable', 'Noto Sans KR', sans-serif;
  font-size: 14px;
  color: rgba(229, 231, 235, 0.95);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 16px;
  box-shadow: 0 4px 18px rgba(0,0,0,0.3), 0 0 12px rgba(100,180,255,0.25);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  animation: fadeUp 1.2s ease both;
  animation-delay: 1.5s;
}
.footer:hover {
  transform: translateY(-4px) scale(1.02);
  box-shadow: 0 6px 24px rgba(0,0,0,0.4), 0 0 18px rgba(100,180,255,0.35);
}

/* Archive button */
.archive-btn {
  position: fixed;
  top: 72px;            
  right: 32px;
  padding: 12px 20px;   
  font-size: 15px;
  font-weight: 600;
  border-radius: 20px;
  background: #FACC15;
  color: #111;
  text-decoration: none;
  box-shadow: 0 4px 14px rgba(0,0,0,0.3);
  transition: transform .25s ease, box-shadow .25s ease;

  display: inline-flex; 
  align-items: center;
  line-height: 1;
  cursor: pointer;

  z-index: 2147483647;   
  pointer-events: auto; 
}

.archive-btn:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.4);
}


.footer {
  margin: 50px auto;
  padding: 22px 28px;
  max-width: 520px;
  text-align: center;
  font-family: 'Pretendard Variable','Noto Sans KR',sans-serif;
  font-size: 15px;
  color: rgba(229, 231, 235, 0.95);
  background: linear-gradient(135deg, rgba(255,255,255,0.07), rgba(255,255,255,0.03));
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 18px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.35), 0 0 14px rgba(120,180,255,0.25);
  transition: transform 0.35s ease, box-shadow 0.35s ease;
  animation: fadeUp 1.2s ease both;
  animation-delay: 1.5s;
}

.footer:hover {
  transform: translateY(-5px) scale(1.02);
  box-shadow: 0 6px 28px rgba(0,0,0,0.4), 0 0 20px rgba(120,180,255,0.4);
}

.footer-title {
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 6px;
  color: #FACC15;
}

.footer-sub {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #A5B4FC;
}

.footer-names {
  font-size: 14px;
  line-height: 1.6;
  color: rgba(229, 231, 235, 0.85);
}


/* 카드 베이스 */
.card{
  display:block; text-decoration:none; color:inherit;
  width:340px; border-radius:18px; overflow:hidden; position:relative;
  background: rgba(255,255,255,0.06);
  border:1px solid rgba(255,255,255,0.16);
  box-shadow: 0 12px 28px rgba(0,0,0,0.22);
  transition: transform .22s ease, box-shadow .22s ease, filter .22s ease;
}
.card:hover{
  transform: translateY(-4px);
  box-shadow: 0 16px 44px rgba(0,0,0,0.32);
}

/* 썸네일: 대비 강화 + 광택 */
.card-thumb{
  height: 188px; width:100%;
  background-size: cover; background-position:center;
  position:relative; isolation:isolate; /* ::before/::after 레이어 분리 */
}
/* 상부 하이라이트 + 미세 노이즈로 골드 질감 살리기 */
.card-thumb::before{
  content:""; position:absolute; inset:0; z-index:0;
  background:
    radial-gradient(120% 60% at 50% -10%, rgba(255,255,255,0.08), transparent 55%),
    linear-gradient(180deg, rgba(0,0,0,0.10) 0%, rgba(0,0,0,0.00) 35%, rgba(0,0,0,0.18) 70%);
}
.card:hover .card-thumb::before{
  background:
    radial-gradient(120% 60% at 50% -10%, rgba(255,255,255,0.12), transparent 55%),
    linear-gradient(180deg, rgba(0,0,0,0.12) 0%, rgba(0,0,0,0.00) 33%, rgba(0,0,0,0.24) 72%);
}

/* 썸네일→본문 연결 그라데이션(경계 자연스럽게) */
.card-thumb::after{
  content:""; position:absolute; left:0; right:0; bottom:-1px; height:90px; z-index:1;
  background: linear-gradient(180deg, rgba(0,0,0,0.00) 0%, rgba(0,0,0,0.22) 70%, rgba(0,0,0,0.35) 100%);
}

/* 바디: 글래스 느낌 + 위쪽 경계 은은하게 */
.card-body{
  position:relative; z-index:2;
  padding: 16px 18px 18px;
  background: linear-gradient(180deg, rgba(16,18,34,0.55) 0%, rgba(16,18,34,0.38) 100%);
  backdrop-filter: blur(6px);
  border-top: 1px solid rgba(255,255,255,0.10);
}

/* 본문 텍스트: 크기/굵기↑ + 섀도우로 선명하게 */
.card-desc{
  font-family: 'Pretendard Variable','Noto Sans KR','Segoe UI',Inter,system-ui,sans-serif;
  font-size: 16px;            /* +1 업 */
  font-weight: 700;
  letter-spacing: .2px;
  line-height: 1.6;
  color: #ECF0FF;             /* 더 밝은 톤 */
  text-shadow: 0 1px 0 rgba(0,0,0,0.28), 0 0 12px rgba(12,16,36,0.35);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

/* 포커스 접근성 */
.card:focus-visible{ outline:2px solid #A78BFA; outline-offset:3px; }

/* 작은 화면 최적화 */
@media (max-width: 768px){
  .card{ width:100%; }
  .card-thumb{ height:170px; }
  .card-desc{ font-size:15px; -webkit-line-clamp:3; }
}




</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# --- HTML BODY ---
HTML_BODY = f"""
<div class="aurora-bg"></div>
<div class="aurora-layer"></div>
<div class="stars"></div>

<a class="archive-btn" href="/?page=4_%EB%82%B4%EA%B0%80_%EC%83%9D%EC%84%B1%ED%95%9C_%EC%9D%B4%EB%AF%B8%EC%A7%80">📂 보관함</a>

<div class="main-block">
  <div class="hero">
    <h1>광고 이미지/글 생성 서비스</h1>
    <p>소상공인을 위한 광고 이미지, 글 그리고 메뉴판 생성 AI</p>
  </div>

  <div class="section-title section-start">시작하기</div>
  <div class="card-row section-start">
    {build_cards_html()}
  </div>

  <div class="section-title section-templates">예시 템플릿</div>
  <div class="template-marquee section-templates">
    <div class="marquee-track">
      {build_templates_html()}
      {build_templates_html()}
    </div>
  </div>

  <div class="footer">
    <div class="footer-title">코드잇 스프린트 2기</div>
    <div class="footer-sub">🌿 4팀 · 나뭇잎 마을 🌿</div>
    <div class="footer-names">👨‍💻 이승종 · 정민영 · 신한호 · 주대성 👩‍💻</div>
  </div>
</div>
"""
st.markdown(HTML_BODY, unsafe_allow_html=True)
