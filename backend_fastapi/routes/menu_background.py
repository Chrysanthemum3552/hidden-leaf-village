from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFilter
import os, random

router = APIRouter()

class Palette(BaseModel):
    bg: Optional[str] = None
    fg: Optional[str] = None
    accent: Optional[str] = None

class BgReq(BaseModel):
    theme: str = "chalkboard"     # "chalkboard" | "retro-cream" | "gradient"
    size: Tuple[int, int] = (1080, 1528)
    seed: Optional[int] = None
    palette: Optional[Palette] = None
    texture: Optional[str] = None  # "paper-grain" | "noise" | "none"
    reference_image_url: Optional[str] = None

def _hex_to_rgb(c: Optional[str], default):
    if not c:
        return default
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))

def make_chalkboard(sz, palette: Palette):
    bg = _hex_to_rgb(getattr(palette, "bg", None), (20, 22, 24))
    img = Image.new("RGB", sz, bg)
    overlay = Image.new("RGB", sz, (255, 255, 255)).filter(ImageFilter.GaussianBlur(4))
    img = Image.blend(img, overlay, 0.03)
    w, h = sz
    v = Image.new("L", sz, 0)
    d = ImageDraw.Draw(v)
    d.ellipse((-int(w*0.2), -int(h*0.2), int(w*1.2), int(h*1.2)), fill=255)
    v = v.filter(ImageFilter.GaussianBlur(60))
    img.putalpha(v)
    return img.convert("RGB")

def make_retro_cream(sz, palette: Palette):
    bg = _hex_to_rgb(getattr(palette, "bg", None), (245, 238, 226))
    img = Image.new("RGB", sz, bg)
    paper = Image.new("RGB", sz, (235, 230, 220)).filter(ImageFilter.GaussianBlur(2))
    img = Image.blend(img, paper, 0.08)
    d = ImageDraw.Draw(img)
    w, h = sz
    for _ in range(int(w*h/20000)):
        x, y = random.randint(0, w-1), random.randint(0, h-1)
        d.point((x, y), fill=(max(bg[0]-12,0), max(bg[1]-12,0), max(bg[2]-12,0)))
    return img

def make_gradient(sz, palette: Palette):
    start = _hex_to_rgb(getattr(palette, "bg", None), (17, 24, 39))
    end   = _hex_to_rgb(getattr(palette, "accent", None), (79, 70, 229))
    w, h = sz
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        r = int(start[0]*(1-t) + end[0]*t)
        g = int(start[1]*(1-t) + end[1]*t)
        b = int(start[2]*(1-t) + end[2]*t)
        draw.line((0, y, w, y), fill=(r, g, b))
    return img

@router.post("/menu-background")
def make_menu_background(req: BgReq):
    random.seed(req.seed or 42)
    w, h = req.size
    pal = req.palette or Palette()

    if req.theme == "chalkboard":
        img = make_chalkboard((w, h), pal)
    elif req.theme == "retro-cream":
        img = make_retro_cream((w, h), pal)
    else:
        img = make_gradient((w, h), pal)

    if req.texture in ("paper-grain", "noise"):
        img = img.filter(ImageFilter.GaussianBlur(0.4))

    storage = os.getenv(
        "STORAGE_ROOT",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    )
    out_dir = os.path.join(storage, "outputs")
    os.makedirs(out_dir, exist_ok=True)

    fname = f"bg_{req.theme}_{w}x{h}_{random.randint(0, 999999):06}.png"
    path = os.path.join(out_dir, fname)
    img.save(path, "PNG")

    base = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
    return {"ok": True, "background_url": f"{base}/static/outputs/{fname}"}