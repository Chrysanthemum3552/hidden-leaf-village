import streamlit as st
from urllib.parse import quote
import html, os

st.set_page_config(page_title="광고 생성 도우미", layout="wide", initial_sidebar_state="collapsed")

# --- 쿼리 → switch_page 라우팅 ---
q = st.query_params
page_key = q.get("page")
if page_key:
    st.switch_page(f"pages/{page_key}.py")

# --- 데이터 ---
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "https://hidden-leaf-village.onrender.com").rstrip("/")

PAGES = [
    {"badge":"🖼️ IMAGE","thumb":f"{BACKEND_PUBLIC_URL}/static/images/1.png","title":"광고 이미지 생성","desc":"문구만 입력하면 그에 맞는 광고 이미지를 자동 생성합니다."},
    {"badge":"✍️ COPY","thumb":f"{BACKEND_PUBLIC_URL}/static/images/2.png","title":"광고 글 생성","desc":"이미지/키워드 기반으로 그에 딱 맞는 광고글을 생성합니다."},
    {"badge":"🧾 MENU","thumb":f"{BACKEND_PUBLIC_URL}/static/images/3.png","title":"메뉴판 생성","desc":"메뉴와 가격을 입력하면 그에 맞는 메뉴판을 만듭니다."},
]

EXAMPLE_FILES = [f"example_{i}.png" for i in range(1, 9)]
SAMPLES = [(f"{BACKEND_PUBLIC_URL}/static/outputs/{fname}", f"Example {i}") for i, fname in enumerate(EXAMPLE_FILES, start=1)]

ROUTES = {
    "광고 이미지 생성":"1_광고_이미지_생성",
    "광고 글 생성":"2_광고_글_생성",
    "메뉴판 생성":"3_메뉴판_생성",
}

# --- builders ---
def build_cards_html():
    items = []
    for c in PAGES:
        key = ROUTES[c["title"]]
        href = f"/?page={quote(key)}"
        items.append(f"""
<a class="card" href="{href}" aria-label="{html.escape(c['title'])}">
  <div class="card-head">
    <div class="card-icon-wrap">
      <img class="card-icon" src="{c['thumb']}" alt="" loading="lazy" decoding="async">
    </div>
    <div class="card-title">{html.escape(c["title"])}</div>
  </div>
  <div class="card-desc">{html.escape(c["desc"])}</div>
  <div class="card-cta">
    <span class="cta-icon">▶</span> <span class="cta-text">바로 시작하기</span>
  </div>
</a>
""")
    return "".join(items)




def build_templates_html():
    cards=[]
    for url, cap in SAMPLES:
        cap_esc = html.escape(cap, quote=True)
        cards.append(f"""
<div class="template"><img src="{url}" alt="{cap_esc}" loading="lazy" decoding="async"></div>
""".strip())
    return "\n".join(cards)

# --- (옵션) 폰트 ---
FONT_CSS = f"""
<style>
@font-face {{
  font-family:'SUIT';
  src:url('{BACKEND_PUBLIC_URL}/static/fonts/SUIT-Variable.woff2') format('woff2-variations');
  font-weight:100 900; font-style:normal; font-display:swap;
}}
@font-face {{
  font-family:'GmarketSans';
  src:url('{BACKEND_PUBLIC_URL}/static/fonts/GmarketSansBold.woff2') format('woff2');
  font-weight:800; font-style:normal; font-display:swap;
}}
:root {{
  --font-ui:'SUIT',system-ui,-apple-system,'Noto Sans KR',sans-serif;
  --font-title:'GmarketSans','SUIT',system-ui,sans-serif;
}}
body,.stApp,.block-container{{font-family:var(--font-ui);}}
</style>"""
st.markdown(FONT_CSS, unsafe_allow_html=True)

# --- CSS ---
CSS = """
<style>
:root {
  --bg1:#eaf2ff;
  --bg2:#fbfbff;
  --ink-1:#0f172a;
  --ink-2:#334155;
  --card:#fff;
  --line:#e5e7eb;
  --elev:0 6px 18px rgba(15,23,42,.08);
  --elev2:0 12px 28px rgba(15,23,42,.12);
  --radius:18px;
  --gutter-l:clamp(4px,7vw,36px);
  --gutter-r:clamp(16px,4vw,40px);
  /* 타이틀 어두운 프리미엄 그라데이션 */
  --title-a:#0b1b3a;
  --title-b:#223a8a;
  --title-c:#0f766e;
}

/* reset */
html, body {
  margin:0;
  padding:0;
}
.stApp, .block-container {
  background:transparent !important;
}
* {
  box-sizing:border-box;
}
img {
  display:block;
  max-width:100%;
}

/* background */
.aurora-bg {
  position:fixed;
  inset:0;
  z-index:-2;
  background:
    radial-gradient(1200px 800px at 10% 0%, #cfe7ff 0%, transparent 55%),
    radial-gradient(900px 700px at 85% 15%, #eadcff 0%, transparent 60%),
    linear-gradient(180deg, var(--bg1), var(--bg2));
}

/* container left-anchored */
.main-block {
  max-width:none;
  margin:0;
  padding:56px var(--gutter-r) 64px var(--gutter-l);
}

/* stray inline-code kill (</div> 같은 잔상 숨김) */
.main-block code {
  display:none !important;
}

/* reveal group animation (0.5s 간격) */
.reveal {
  opacity:0;
  transform:translateY(16px);
  animation:reveal .6s ease forwards;
}
.delay-0 { animation-delay:0s }
.delay-1 { animation-delay:.5s }
.delay-2 { animation-delay:1s }
.delay-3 { animation-delay:1.5s }

@keyframes reveal {
  to {
    opacity:1;
    transform:translateY(0);
  }
}

/* hero */
.hero {
  text-align:center;
  margin:12px 0 6px;
}
.hero h1 {
  font-family:var(--font-title);
  font-weight:800;
  font-size:clamp(44px,7vw,86px);
  line-height:1.03;
  letter-spacing:-.02em;
  background:linear-gradient(100deg,var(--title-a),var(--title-b) 55%,var(--title-c));
  -webkit-background-clip:text;
  -webkit-text-fill-color:transparent;
  text-shadow:0 2px 8px rgba(17,24,39,.14), 0 0 22px rgba(99,102,241,.10);
  margin:0 0 12px;
}
.hero p {
  color:var(--ink-2);
  font-weight:600;
  font-size:clamp(14px,1.6vw,18px);
  margin:0 0 0 8px;
}

/* section titles */
.section {
  margin-top:48px;
}
.section-inner{
  max-width: calc(400px * 3 + 16px * 2);
  margin: 0 auto;
}


/* 제목은 계속 왼쪽 */
.section-title{
  font-family: var(--font-title); 
  font-weight: 800;              
  font-size: 25px; 
  line-height: 1.2;
  color: var(--ink-1);
  text-align: left;              
  margin: 18px 0 10px 4px;       
  letter-spacing: -0.2px;
}
.section-title::after {
  content:"";
  display:block;
  width:105px;
  height:3px;
  margin:10px 0 15px 0;
  border-radius:2px;
  background:linear-gradient(90deg,#60a5fa,#a78bfa,#34d399);
}

/* cards grid */
.card-row{
  display: grid;
  grid-template-columns: repeat(3, 400px);  /* ← auto-fill 대신 3칸 고정 */
  gap: 16px;
  justify-content: center;                  /* 가운데 정렬 */
}
.card-row > :not(a.card) {
  display:none !important;
}

/* 카드 */
.card {
  display:flex;
  flex-direction:column;   /* 제목, 설명, CTA 순서대로 쌓임 */
  text-decoration:none;
  color:inherit;
  border-radius:var(--radius);
  background:rgba(255,255,255,0.75);
  backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px);
  border:1px solid rgba(255,255,255,0.45);
  box-shadow:0 10px 24px rgba(15,23,42,.12);
  padding:18px 20px;
  transition:transform .22s ease, box-shadow .22s ease;
}
.card:hover {
  transform:translateY(-6px) scale(1.02);
  box-shadow:0 16px 36px rgba(15,23,42,.18);
}

/* 헤더 (아이콘 + 제목 한 줄) */
.card-head {
  display:flex;
  align-items:center;
  gap:10px;
  margin-bottom:8px;
}
.card-icon {
  width:56px;
  height:56px;
  flex:0 0 56px;
  object-fit:contain;
}
.card-title {
  font-weight:600;
  color:var(--ink-1);
  font-size:25px;
  line-height:1.3;
}

/* 설명 */
.card-desc {
  font-weight:600;
  color:var(--ink-2);
  font-size:14px;
  line-height:1.55;
}

/* CTA 버튼 */
.card-cta {
  display:inline-flex;
  align-items:center;
  gap:8px;
  margin-top:60px;

  margin-left:auto;   /* 버튼만 오른쪽으로 이동 */

  padding:10px 14px;
  border-radius:10px;
  background:#111;
  color:#fff;
  font-weight:600;
  font-size:14px;
  transition:background .2s, transform .2s;
  width:max-content;
}


.card-cta:hover {
  background:#000;
  transform:translateY(-2px);
}

/* CTA 아이콘 */
.cta-icon {
  font-size:14px;
  line-height:1;
}
.cta-text {
  line-height:1.3;
}



/* 예시 템플릿: 마키 + 가장자리 페이드 */
.template-marquee {
  position:relative;
  overflow:hidden;
  padding:14px 0 0;
  max-width:calc(400px * 3 + 16px * 2);
}
.marquee-track {
  display:flex;
  gap:14px;
  width:max-content;
  will-change:transform;
  animation:marquee 40s linear infinite;
}
.template-marquee:hover .marquee-track {
  animation-play-state:paused;
}
.template {
  background:#fff;
  border:1px solid var(--line);
  border-radius:14px;
  box-shadow:var(--elev);
  overflow:hidden;
}
.template img {
  width:220px;
  height:auto;
  display:block;
}
.template-marquee::before,
.template-marquee::after {
  content:"";
  position:absolute;
  top:0;
  bottom:0;
  width:80px;
  pointer-events:none;
  z-index:2;
}
.template-marquee::before {
  left:0;
  background:linear-gradient(to right, rgba(234,242,255,1), rgba(234,242,255,0));
}
.template-marquee::after {
  right:0;
  background:linear-gradient(to left, rgba(251,251,255,1), rgba(251,251,255,0));
}
@keyframes marquee {
  0% { transform:translateX(-50%) }
  100% { transform:translateX(0%) }
}

/* footer (밴드형) */
.footer {
  max-width:720px;
  margin:100px auto 72px;
  padding:22px 28px;
  text-align:center;
  border-radius:20px;
  border:2px solid transparent;
  background:
    linear-gradient(180deg, rgba(255,255,255,0.72), rgba(255,255,255,0.56)) padding-box,
    linear-gradient(135deg, var(--brand-1), var(--brand-2), var(--brand-3)) border-box;
  box-shadow:
    0 10px 28px rgba(15,23,42,.12),
    0 1px 0 rgba(255,255,255,.6) inset;
  backdrop-filter:blur(6px);
  -webkit-backdrop-filter:blur(6px);
  color:var(--ink-1);
  font-weight:700;
  line-height:1.7;
  background-clip:padding-box, border-box;
  border-top:none;
}
.footer b {
  font-size:18px;
  color:var(--ink-1);
}
@media (max-width:560px) {
  .footer {
    max-width:100%;
    margin:32px var(--gutter-r);
    padding:18px 20px;
  }
}

/* archive btn */
.archive-btn {
  position:fixed;
  top:36px;
  right:32px;
  padding:12px 20px;
  border-radius:999px;
  line-height:1;
  background:#ffffff;
  color:#0f172a;
  font-weight:800;
  text-decoration:none;
  border:3px solid #F59E0B;
  box-shadow:0 8px 20px rgba(15,23,42,.10), inset 0 0 0 2px #fff;
  z-index:2147483647;
  transition:.15s;
}
.archive-btn:hover {
  transform:translateY(-2px);
  box-shadow:0 12px 28px rgba(15,23,42,.16), inset 0 0 0 2px #fff;
}
.archive-btn:focus-visible {
  outline:3px solid #F59E0B;
  outline-offset:3px;
}

/* streamlit header clear */
.stApp > header {
  background:transparent;
}
</style>

"""
st.markdown(CSS, unsafe_allow_html=True)

# --- HTML BODY ---
HTML_BODY = f"""
<div class="aurora-bg"></div>
<a class="archive-btn" href="/?page=4_%EB%82%B4%EA%B0%80_%EC%83%9D%EC%84%B1%ED%95%9C_%EC%9D%B4%EB%AF%B8%EC%A7%80">📂 보관함</a>

<div class="main-block">
  <!-- 1) 제목+부제 -->
  <div class="hero reveal delay-0">
    <h1>광고 이미지/글 생성 서비스</h1>
    <p>소상공인을 위한 광고 이미지, 글 그리고 메뉴판 생성 AI</p>
  </div>

  <!-- 2) 시작하기 + 카드들 -->
  <div class="section reveal delay-1">
    <div class="section-inner">
      <div class="section-title">시작하기</div>
      <div class="card-row">
        { build_cards_html() }
      </div>
    </div>
  </div>

  <!-- 3) 예시 모음 -->
  <div class="section reveal delay-2">
    <div class="section-inner">
      <div class="section-title">예시 모음</div>
      <div class="template-marquee">
        <div class="marquee-track">
          { build_templates_html() }
          { build_templates_html() }
        </div>
      </div>
    </div>
  </div>

  <!-- 4) 만든 사람들 -->
  <div class="footer reveal delay-3">
    <div><b>코드잇 스프린트 2기</b> <br> 🌿 4팀 · 나뭇잎 마을 <br> 이승종 · 정민영 · 신한호 · 주대성</div>
  </div>
</div>
"""
st.markdown(HTML_BODY, unsafe_allow_html=True)
