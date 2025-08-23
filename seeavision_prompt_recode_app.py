# seeavision_prompt_styler_recode_pro.py
# -------------------------------------------------------------------
# Prompt Styler + Recode 4.0 — Pro (single-file Streamlit app)
#
# What this app does
#   • Rates the ORIGINAL prompt first: Toxicity, Disruption, Positivity
#   • Two modes:
#       1) Style My Original (no AI needed)  → turns your exact text into poster-ready formats
#       2) Recode Then Style (needs OpenAI)  → creates aligned alternatives, then styles them
#   • Emoji-aligned styles + clean, high-contrast UI (mobile friendly)
#   • Per-alternative improvement metrics (+/- %) after recode
#   • Exports: copy text, download TXT/JSON, and PNG image tiles
#
# Quickstart:
#   pip install streamlit openai pillow
#   export OPENAI_API_KEY=your_key   # only required for "Recode Then Style"
#   streamlit run seeavision_prompt_styler_recode_pro.py
# -------------------------------------------------------------------

import os, re, io, json, textwrap
from typing import List, Dict, Any, Tuple
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# Optional OpenAI (only used in "Recode Then Style")
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if (OpenAI and OPENAI_API_KEY) else None

# ---------- Tone-appropriate emoji map ----------
EMOJI_MAP = {
    "Serious & Balanced": "⚖️",
    "Collaborative Debate": "🤝",
    "Comedic Spin": "😂",
    "Uplifting Alternative": "🌟",
    "Educational Insight": "📘",
    "Thought-Provoking": "🤔",
}

# ---------- Style presets & formatter ----------
STYLE_PRESETS = {
    "Big Bold Banner":     {"case":"upper",    "prefix":"",   "bullets":False},
    "Fire Headline":       {"case":"title",    "prefix":"🔥 ", "bullets":False},
    "Minimal Stack":       {"case":"title",    "prefix":"",   "bullets":False},
    "Debate Ticket":       {"case":"title",    "prefix":"",   "bullets":True },
    "Sticker Bubble":      {"case":"mixed",    "prefix":"🗯️ ", "bullets":False},
    "Clean Serif":         {"case":"sentence", "prefix":"",   "bullets":False},
    "Neon Dark":           {"case":"upper",    "prefix":"⚡ ", "bullets":False},
    "Q&A Card":            {"case":"title",    "prefix":"❓ ", "bullets":False},
}

def _to_case(text: str, mode: str) -> str:
    if mode == "upper": return text.upper()
    if mode == "title": return text.title()
    if mode == "sentence":
        t = text.strip()
        return (t[:1].upper() + t[1:]) if t else t
    return text  # mixed

def _smart_lines(core: str, max_lines: int = 5) -> List[str]:
    # try punctuation split first
    parts = re.split(r"[.,;:!?]\s+|\s{2,}", core.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 3:
        words = core.split()
        if not words:
            return []
        step = max(1, len(words)//3)
        parts = [" ".join(words[i:i+step]) for i in range(0, len(words), step)]
    return parts[:max_lines]

def format_prompt_for_style(text: str, preset_name: str) -> str:
    p = STYLE_PRESETS[preset_name]
    if p["bullets"]:
        lines = _smart_lines(text, max_lines=3)
        headline = _to_case(lines[0], p["case"]) if lines else _to_case(text, p["case"])
        subs = lines[1:3] if len(lines) > 1 else ["Share your view", "Bring one solution"]
        subs = [f"• {s}" for s in subs]
        return f"{headline}\n" + "\n".join(subs)
    else:
        lines = _smart_lines(text, max_lines=5)
        lines = [_to_case(l, p["case"]) for l in lines] if lines else [_to_case(text, p["case"])]
        if p["prefix"]:
            lines[0] = f"{p['prefix']}{lines[0]}"
        return "\n".join(lines)

# ---------- Page / Global Styles (visibility fixes) ----------
st.set_page_config(page_title="Prompt Styler + Recode 4.0 — Pro", page_icon="✨", layout="wide")
st.markdown("""
<style>
body, .stApp { background:#fff !important; color:#111 !important; font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; }
h1,h2,h3,h4 { color:#2b2b6e; font-weight:700; }
hr { border:none; height:1px; background:#eee; margin:16px 0; }
.stTextArea textarea, .stTextInput input { background:#fff !important; color:#111 !important; border:1px solid #d9d9d9 !important; border-radius:12px !important; font-size:16px !important; }
.stTextArea textarea::placeholder { color:#777 !important; }
.stButton>button { background:#f5c518 !important; color:#111 !important; border:none !important; border-radius:12px !important; font-weight:700 !important; padding:.65em 1.2em; box-shadow:0 2px 5px rgba(0,0,0,.08); }
.stButton>button:hover { background:#ffd84d !important; }
.card { background:#fafafa; border:1px solid #eee; border-radius:14px; padding:14px 16px; box-shadow:0 2px 4px rgba(0,0,0,.04); margin-bottom:12px; }
.metric { display:flex; gap:10px; flex-wrap:wrap; }
.metric .pill { background:#fff; border:1px solid #eee; border-radius:999px; padding:6px 12px; font-weight:600; box-shadow:0 1px 2px rgba(0,0,0,.03); }
.stAlert { background:#ffecec !important; border:1px solid #f5b5b5 !important; border-radius:12px !important; }
</style>
""", unsafe_allow_html=True)

# ---------- Heuristic analyzer ----------
TOXIC_WORDS = {"hate","stupid","idiot","disgusting","trash","fake","owe","jealous","disrespect","loser","dumb","evil","attack","fraud","lazy"}
DISRUPT_WORDS = {"vs","versus","against","beef","war","takedown","clapback","exposed","owe","fake","divide","enemy"}

def analyze_text(text: str) -> Dict[str, int]:
    t = text.lower()
    tox_hits = sum(1 for w in TOXIC_WORDS if re.search(rf"\b{re.escape(w)}\b", t))
    dis_hits = sum(1 for w in DISRUPT_WORDS if re.search(rf"\b{re.escape(w)}\b", t))
    exclam = t.count("!")
    letters = sum(1 for c in text if c.isalpha())
    caps_ratio = sum(1 for c in text if c.isupper()) / letters if letters else 0
    toxicity = int(min(100, tox_hits*12 + exclam*3 + caps_ratio*20))
    disruption = int(min(100, dis_hits*10 + caps_ratio*10))
    positivity = int(max(0, 100 - toxicity))
    return {"toxicity": toxicity, "disruption": disruption, "positivity": positivity, "length": len(text)}

def improvement(before: Dict[str,int], after: Dict[str,int]) -> Dict[str,str]:
    tox_red = max(0, before["toxicity"] - after["toxicity"])
    dis_red = max(0, before["disruption"] - after["disruption"])
    pos_inc = max(0, after["positivity"] - before["positivity"])
    return {
        "toxicity_reduction": f"-{tox_red}%",
        "disruption_reduction": f"-{dis_red}%",
        "positivity_increase": f"+{pos_inc}%"
    }

# ---------- OpenAI recode (robust JSON; strips ```json fences) ----------
def _strip_code_fences(s: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", s, flags=re.S | re.I)
    return m.group(1).strip() if m else s.strip()

def generate_recodes(original: str, n_variants: int = 4) -> List[Dict[str,str]]:
    if not client:
        st.error("Missing `OPENAI_API_KEY`. Add it to Environment (or switch to 'Style My Original').")
        st.stop()

    input_len = len(original)
    target_len = input_len
    low = original.lower()
    if re.search(r"\b(short|shorten|condense)\b", low):
        target_len = max(200, int(input_len*0.6))
    elif re.search(r"\b(long|expand|detailed|thread)\b", low):
        target_len = int(input_len*1.5)

    system = f"""
You are "Prompt Recode 4.0 — Pro".
Rewrite an input prompt into multiple aligned alternatives that keep the topic but remove hostility and confusion.

Rules:
- Keep the cultural voice; do NOT punch down.
- Auto-match output length to the input (~{target_len} chars) unless the input says to shorten/expand.
- Output JSON ONLY: a list of objects with keys: style, emoji, text.
- Styles to include at least once: "Serious & Balanced", "Collaborative Debate", "Comedic Spin", "Uplifting Alternative".
- Each 'text' must be one paragraph, ready to copy/paste.
"""
    user = f"Original prompt:\n{original}\n\nReturn a JSON list with {n_variants}–6 alternatives."

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            temperature=0.7,
            max_tokens=max(1200, target_len*2)
        )
        content = _strip_code_fences(resp.choices[0].message.content or "")
    except Exception:
        st.error("Authentication failed. Verify `OPENAI_API_KEY` and redeploy.")
        st.stop()

    variants: List[Dict[str,str]] = []
    try:
        data = json.loads(content)
        for item in data:
            style = str(item.get("style","Recode")).strip()
            emoji = EMOJI_MAP.get(style, item.get("emoji","✨")).strip()
            text  = str(item.get("text","")).strip()
            if text:
                variants.append({"style":style, "emoji":emoji, "text":text})
    except Exception:
        # fallback parsing
        blocks = re.split(r"\n\s*\n", content)
        for b in blocks:
            if not b.strip(): continue
            m = re.match(r"\s*(.+?):\s*(.+)", b.strip(), flags=re.S)
            if m:
                style, text = m.group(1).strip(), m.group(2).strip()
            else:
                style, text = "Recode", b.strip()
            variants.append({"style":style, "emoji":EMOJI_MAP.get(style,"✨"), "text":text})

    variants = variants[:max(n_variants, 4)]
    hard_max = int(target_len * (1.5 if re.search(r"\b(long|expand|detailed|thread)\b", low) else 1.1)) + 40
    for v in variants:
        if len(v["text"]) > hard_max:
            v["text"] = v["text"][:hard_max].rstrip()
    return variants

# ---------- Image tile rendering ----------
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    # Try DejaVuSans (present in many environments); fallback to default bitmap
    for fpath in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                  "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]:
        if os.path.exists(fpath):
            return ImageFont.truetype(fpath, size=size)
    return ImageFont.load_default()

def wrap_text_for_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    lines = []
    for raw_line in text.split("\n"):
        words = raw_line.split(" ")
        buf = ""
        for w in words:
            test = (buf + " " + w).strip()
            if draw.textlength(test, font=font) <= max_width:
                buf = test
            else:
                if buf: lines.append(buf)
                buf = w
        if buf: lines.append(buf)
    return "\n".join(lines)

def render_tile_png(
    text: str,
    width: int = 1080,
    padding: int = 72,
    bg: str = "#0f172a",        # slate-900 default (for punch)
    fg: str = "#f8fafc",        # slate-50
    accent: str = "#f5c518",    # gold
    rounded: int = 36,
    title_emoji: str = ""
) -> bytes:
    font_big = _load_font(72)
    font_body = _load_font(64)

    img = Image.new("RGB", (width, 1), color=bg)
    draw = ImageDraw.Draw(img)

    # compute wrapped text height
    text_wrapped = wrap_text_for_width(draw, text, font_body, width - 2*padding)
    _, _, w, h = draw.multiline_textbbox((0,0), text_wrapped, font=font_body, spacing=10)

    height = padding*2 + h + (0 if not title_emoji else 80)
    img = Image.new("RGB", (width, height), color=bg)
    draw = ImageDraw.Draw(img)

    # header line
    if title_emoji:
        draw.text((padding, padding-16), title_emoji, font=font_big, fill=accent)

    # body
    y_start = padding + (0 if not title_emoji else 56)
    # optional rounded border
    try:
        draw.rounded_rectangle(
            (padding-20, y_start-20, width-padding+20, y_start+h+20),
            radius=rounded, outline=accent, width=4
        )
    except Exception:
        pass
    draw.multiline_text((padding, y_start), text_wrapped, font=font_body, fill=fg, spacing=10)

    # export
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

# ---------- APP ----------
st.title("✨ Prompt Styler + Recode 4.0 — Pro")
st.caption("Choose: keep your original (style it) or generate aligned alternatives, then style & export as PNG.")

mode = st.radio("Mode", ["Style My Original (no AI needed)", "Recode Then Style (uses AI)"])
user_prompt = st.text_area("Paste a prompt/topic", height=180, placeholder="e.g. WHY DO WE NEED APPROVAL TO WIN?")
include_comedy = st.checkbox("Include a playful/comedic alternative (recode mode)", value=True)

# Ratings always shown for the original
if user_prompt.strip():
    orig = analyze_text(user_prompt)
    st.markdown("### 🔍 Original Analysis")
    st.markdown(
        f"""
        <div class="card">
          <div class="metric">
            <div class="pill">⚠️ Toxicity: <b>{orig['toxicity']}%</b></div>
            <div class="pill">🔥 Disruption: <b>{orig['disruption']}%</b></div>
            <div class="pill">🌱 Positivity Potential: <b>{orig['positivity']}%</b></div>
            <div class="pill">🔠 Length: <b>{orig['length']}</b> chars</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ---- STYLE MY ORIGINAL ----
if mode.startswith("Style"):
    st.markdown("### 🎨 Style Your Original")
    style_choice = st.selectbox("Choose a style preset", list(STYLE_PRESETS.keys()), index=0)
    theme = st.selectbox("PNG Theme", ["Dark (punchy)", "Light (clean)"], index=0)

    styled = format_prompt_for_style(user_prompt, style_choice) if user_prompt.strip() else ""
    if styled:
        st.markdown("**Preview**")
        st.markdown(f"<div class='card'><pre style='white-space:pre-wrap;font-family:inherit;margin:0'>{styled}</pre></div>",
                    unsafe_allow_html=True)

        st.download_button("📄 Download TXT", data=styled, file_name=f"styled_{style_choice.replace(' ','_').lower()}.txt", mime="text/plain")

        bg = "#0f172a" if theme.startswith("Dark") else "#ffffff"
        fg = "#f8fafc" if theme.startswith("Dark") else "#111111"
        png_bytes = render_tile_png(styled, bg=bg, fg=fg, title_emoji="")
        st.download_button("🖼️ Download PNG Tile", data=png_bytes, file_name=f"styled_{style_choice.replace(' ','_').lower()}.png", mime="image/png")

# ---- RECODE THEN STYLE ----
else:
    n_variants = 4 if include_comedy else 3
    if st.button("Recode it ✨", type="primary"):
        if not user_prompt.strip():
            st.error("Please paste a prompt or topic.")
            st.stop()

        with st.spinner("Generating alternatives…"):
            recodes = generate_recodes(user_prompt, n_variants=n_variants)

        st.markdown("### ✨ Alternatives (pick a style & export)")
        pack = {"original":{"text":user_prompt,"scores":orig},"alternatives":[]}

        for rec in recodes:
            now = analyze_text(rec["text"])
            gains = improvement(orig, now)

            st.markdown(
                f"""
                <div class="card">
                  <div style="font-size:18px;font-weight:800;margin-bottom:6px;">
                    {EMOJI_MAP.get(rec['style'], rec['emoji'])} <b>{rec['style']}</b>
                  </div>
                  <div style="white-space:pre-wrap;line-height:1.45;margin:6px 0 10px 0;">{rec['text']}</div>
                  <div class="metric">
                    <div class="pill">⚠️ Toxicity now: <b>{now['toxicity']}%</b></div>
                    <div class="pill">🔥 Disruption now: <b>{now['disruption']}%</b></div>
                    <div class="pill">🌱 Positivity now: <b>{now['positivity']}%</b></div>
                  </div>
                  <div class="metric" style="margin-top:8px;">
                    <div class="pill">✅ Toxicity reduced: <b>{gains['toxicity_reduction']}</b></div>
                    <div class="pill">✅ Disruption reduced: <b>{gains['disruption_reduction']}</b></div>
                    <div class="pill">✅ Positivity increased: <b>{gains['positivity_increase']}</b></div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            # Style picker + previews/exports
            st.markdown("**Choose a style**")
            style_choice = st.selectbox(
                f"Style for: {rec['style']}",
                list(STYLE_PRESETS.keys()),
                key=f"style_{rec['style']}_{hash(rec['text'])}"
            )
            theme = st.selectbox("PNG Theme", ["Dark (punchy)", "Light (clean)"], key=f"theme_{hash(rec['text'])}")

            styled_text = format_prompt_for_style(rec["text"], style_choice)
            st.markdown(
                f"<div class='card' style='background:#fff;border:1px dashed #ccc;'><div style='font-weight:800;margin-bottom:6px'>Preview — {style_choice}</div><pre style='white-space:pre-wrap;font-family:inherit;margin:0'>{styled_text}</pre></div>",
                unsafe_allow_html=True
            )

            # text + png downloads
            st.download_button("📄 Download TXT", data=styled_text,
                               file_name=f"{rec['style'].replace(' ','_').lower()}_{style_choice.replace(' ','_').lower()}.txt",
                               mime="text/plain", key=f"txt_{hash(styled_text)}")

            bg = "#0f172a" if theme.startswith("Dark") else "#ffffff"
            fg = "#f8fafc" if theme.startswith("Dark") else "#111111"
            png_bytes = render_tile_png(styled_text, bg=bg, fg=fg, title_emoji="")
            st.download_button("🖼️ Download PNG Tile", data=png_bytes,
                               file_name=f"{rec['style'].replace(' ','_').lower()}_{style_choice.replace(' ','_').lower()}.png",
                               mime="image/png", key=f"png_{hash(styled_text)}")

            pack["alternatives"].append({
                "style": rec["style"],
                "emoji": EMOJI_MAP.get(rec["style"], rec["emoji"]),
                "raw_text": rec["text"],
                "styled_choice": style_choice,
                "styled_text": styled_text,
                "scores": now,
                "improvements": gains
            })

        # JSON export of the whole batch
        st.download_button(
            "⬇️ Download JSON pack",
            data=json.dumps(pack, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="prompt_recode_pack.json",
            mime="application/json"
        )

st.markdown("---")
st.caption("© 2025 Prompt Styler + Recode 4.0 — Pro")
