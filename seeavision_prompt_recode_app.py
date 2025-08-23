# seeavision_prompt_styler_recode_pro.py
# -------------------------------------------------------------------
# Prompt Styler + Recode 4.0 — Pro (stateful, virality rating, copy)
# -------------------------------------------------------------------

import os, re, io, json
from typing import List, Dict, Any
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from streamlit.components.v1 import html as st_html

# Optional OpenAI (only used in "Recode Then Style")
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if (OpenAI and OPENAI_API_KEY) else None

# --------------------------- UI THEME ---------------------------
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
.copywrap { margin-top:8px; }
.copybtn { background:#111; color:#fff; border:none; padding:8px 12px; border-radius:10px; font-weight:700; }
.copybtn:hover { opacity:.9; }
.stAlert { background:#ffecec !important; border:1px solid #f5b5b5 !important; border-radius:12px !important; }
</style>
""", unsafe_allow_html=True)

# --------------------------- PRESETS ---------------------------
EMOJI_MAP = {
    "Serious & Balanced": "⚖️",
    "Collaborative Debate": "🤝",
    "Comedic Spin": "😂",
    "Uplifting Alternative": "🌟",
    "Educational Insight": "📘",
    "Thought-Provoking": "🤔",
}

# Expanded style presets (you said some were missing)
STYLE_PRESETS = {
    "Big Bold Banner":     {"case":"upper",    "prefix":"",    "bullets":False},
    "Fire Headline":       {"case":"title",    "prefix":"🔥 ",  "bullets":False},
    "Minimal Stack":       {"case":"title",    "prefix":"",     "bullets":False},
    "Debate Ticket":       {"case":"title",    "prefix":"",     "bullets":True },
    "Sticker Bubble":      {"case":"mixed",    "prefix":"🗯️ ",  "bullets":False},
    "Clean Serif":         {"case":"sentence", "prefix":"",     "bullets":False},
    "Neon Dark":           {"case":"upper",    "prefix":"⚡ ",  "bullets":False},
    "Q&A Card":            {"case":"title",    "prefix":"❓ ",  "bullets":False},
    "Impact Poster":       {"case":"upper",    "prefix":"",     "bullets":False},
    "Magazine Deck":       {"case":"sentence", "prefix":"",     "bullets":False},
    "Ribbon Headline":     {"case":"title",    "prefix":"🏷️ ",  "bullets":False},
    "Headline Stack":      {"case":"title",    "prefix":"",     "bullets":False},
}

def _to_case(text: str, mode: str) -> str:
    if mode == "upper": return text.upper()
    if mode == "title": return text.title()
    if mode == "sentence":
        t = text.strip()
        return (t[:1].upper() + t[1:]) if t else t
    return text  # mixed

def _smart_lines(core: str, max_lines: int = 5) -> List[str]:
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

# --------------------------- ANALYZER ---------------------------
TOXIC_PATTERNS = [
    r"\b(hate|stupid|idiot|loser|trash|dumb|evil|fraud|liar|shut up|disgusting)\b",
    r"\b(kill|shoot|stab|beat|assault|violence|murder)\b",
    r"\b(drugs?|lean|perc|oxy|xan|coke|heroin|meth)\b",
    r"\b(whore|slut|bitch)\b",
    r"\b(lazy|useless|worthless|weak)\b",
]
DISRUPT_PATTERNS = [
    r"\b(vs|versus|against|beef|war|takedown|clapback|exposed|cancel|boycott)\b",
    r"\b(owe|fake|steal|thief|cheat|scam)\b",
    r"[!?]{2,}",
]

def analyze_text(text: str) -> Dict[str, int]:
    t = text.lower()
    tox_hits = sum(len(re.findall(p, t)) for p in TOXIC_PATTERNS)
    dis_hits = sum(len(re.findall(p, t)) for p in DISRUPT_PATTERNS)
    exclam = t.count("!")
    letters = sum(1 for c in text if c.isalpha())
    caps_ratio = sum(1 for c in text if c.isupper()) / letters if letters else 0
    toxicity = int(min(100, tox_hits*10 + exclam*2 + caps_ratio*15))
    disruption = int(min(100, dis_hits*10 + caps_ratio*10))
    positivity = int(max(0, 100 - toxicity))
    return {"toxicity": toxicity, "disruption": disruption, "positivity": positivity, "length": len(text)}

CTA_WORDS = {"share","comment","debate","join","drop","vote","duet","stitch","tag","follow","watch","reply","discuss","weigh in","sound off"}
HOOK_WORDS = {"why","what","how","truth","myth","secret","real","let’s","is it","can we","would you","should we"}

def virality_label(score:int)->str:
    if score >= 80: return "🔥 High"
    if score >= 60: return "✨ Medium"
    return "🧊 Low"

def virality_rating(text:str, tox:int=None, dis:int=None) -> Dict[str,Any]:
    t = text.strip(); tl = t.lower(); length = len(t)
    has_q = "?" in t
    hook_hits = sum(1 for w in HOOK_WORDS if w in tl)
    cta_hits  = sum(1 for w in CTA_WORDS if w in tl)
    emoji_hits = len(re.findall(r"[\U0001F300-\U0001FAFF]", t))
    lines = max(1, t.count("\n")+1)
    caps_words = len(re.findall(r"\b[A-Z]{3,}\b", t))
    caps_bonus = min(3, caps_words) * 3
    caps_penalty = max(0, caps_words-4) * 4
    if length < 40: len_bonus = -10
    elif length <= 240: len_bonus = 12
    elif length <= 500: len_bonus = 6
    else: len_bonus = -8
    avg_words_line = sum(len(l.split()) for l in t.split("\n")) / lines
    clarity = 12 if avg_words_line <= 16 else (6 if avg_words_line <= 22 else -6)
    if dis is None: dis = analyze_text(text)["disruption"]
    if tox is None: tox = analyze_text(text)["toxicity"]
    spice = 10 if 20 <= dis <= 60 else (4 if 60 < dis <= 80 else (-10 if dis > 80 else 0))
    tox_penalty = -min(30, tox // 2)
    line_bonus = 6 if 2 <= lines <= 5 else (0 if lines == 1 else -4)
    emoji_bonus = min(10, emoji_hits * 2)

    base = 40
    score = base + hook_hits*4 + (8 if has_q else 0) + cta_hits*5 + len_bonus + clarity + spice + tox_penalty + line_bonus + emoji_bonus + caps_bonus - caps_penalty
    score = max(0, min(100, int(round(score))))
    reasons = []
    if has_q: reasons.append("question hook")
    if hook_hits: reasons.append("curiosity keywords")
    if cta_hits: reasons.append("CTA present")
    if 2 <= lines <= 5: reasons.append("multi-line format")
    if len_bonus > 0: reasons.append("strong length")
    if emoji_hits: reasons.append("emoji accent")
    if 20 <= dis <= 80: reasons.append("healthy spice")
    if tox > 40: reasons.append("toxicity penalty")
    if dis > 80: reasons.append("overly divisive penalty")
    if caps_penalty: reasons.append("too many ALL CAPS")
    return {"score": score, "label": virality_label(score), "reasons": reasons}

# --------------------------- OPENAI RECODE ---------------------------
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

# --------------------------- IMAGE TILE ---------------------------
def _load_font(size: int) -> ImageFont.FreeTypeFont:
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

def render_tile_png(text: str, width: int = 1080, padding: int = 72,
                    bg: str = "#0f172a", fg: str = "#f8fafc",
                    accent: str = "#f5c518", rounded: int = 36,
                    title_emoji: str = "") -> bytes:
    font_big = _load_font(72)
    font_body = _load_font(64)

    img = Image.new("RGB", (width, 1), color=bg)
    draw = ImageDraw.Draw(img)
    text_wrapped = wrap_text_for_width(draw, text, font_body, width - 2*padding)
    _, _, _, h = draw.multiline_textbbox((0,0), text_wrapped, font=font_body, spacing=10)
    height = padding*2 + h + (0 if not title_emoji else 80)

    img = Image.new("RGB", (width, height), color=bg)
    draw = ImageDraw.Draw(img)
    if title_emoji:
        draw.text((padding, padding-16), title_emoji, font=font_big, fill=accent)
    y_start = padding + (0 if not title_emoji else 56)
    try:
        draw.rounded_rectangle((padding-20, y_start-20, width-padding+20, y_start+h+20),
                               radius=rounded, outline=accent, width=4)
    except Exception:
        pass
    draw.multiline_text((padding, y_start), text_wrapped, font=font_body, fill=fg, spacing=10)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

# --------------------------- UTIL (copy / fmt) ---------------------------
def copy_box(text: str, key: str, note: str = "Copy-ready text"):
    st.markdown(f"**{note}**")
    st.code(text)
    st_html(f"""
      <div class="copywrap">
        <button class="copybtn" onclick="navigator.clipboard.writeText(`{text.replace('`','\\`')}`)">📋 Copy to Clipboard</button>
      </div>
    """, height=40)

def fmt_delta(n: int) -> str:
    # avoid -0% displaying
    if n == 0: return "0%"
    return f"{'+' if n>0 else ''}{n}%"

# --------------------------- STATE HELPERS ---------------------------
def init_state():
    defaults = {
        "orig_prompt": "",
        "orig_scores": None,
        "orig_viral": None,
        "recodes": None,
        "pack": None,
        "generated": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

def set_prompt(p: str):
    if p != st.session_state.orig_prompt:
        st.session_state.orig_prompt = p
        st.session_state.orig_scores = analyze_text(p) if p.strip() else None
        st.session_state.orig_viral = virality_rating(p) if p.strip() else None
        st.session_state.recodes = None
        st.session_state.pack = None
        st.session_state.generated = False

# --------------------------- APP BODY ---------------------------
st.title("✨ Prompt Styler + Recode 4.0 — Pro")
st.caption("Rate → (optionally) recode → style → export PNG. Copy-ready boxes included.")

mode = st.radio("Mode", ["Style My Original (no AI needed)", "Recode Then Style (uses AI)"])
user_prompt = st.text_area("Paste a prompt/topic", value=st.session_state.orig_prompt,
                           height=180, placeholder="e.g. WHY DO WE NEED APPROVAL TO WIN?")
set_prompt(user_prompt)
include_comedy = st.checkbox("Include a playful/comedic alternative (recode mode)", value=True)

# Original analysis
if st.session_state.orig_scores:
    o = st.session_state.orig_scores
    v = st.session_state.orig_viral
    st.markdown("### 🔍 Original Analysis")
    st.markdown(
        f"""
        <div class="card">
          <div class="metric">
            <div class="pill">⚠️ Toxicity: <b>{o['toxicity']}%</b></div>
            <div class="pill">🔥 Disruption: <b>{o['disruption']}%</b></div>
            <div class="pill">🌱 Positivity Potential: <b>{o['positivity']}%</b></div>
            <div class="pill">🧲 Virality: <b>{v['score']}%</b> ({v['label']})</div>
            <div class="pill">🔠 Length: <b>{o['length']}</b> chars</div>
          </div>
          <div style="margin-top:6px; font-size:14px; opacity:.9;">
            <b>Why:</b> {" • ".join(v['reasons'])}
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ---- STYLE MY ORIGINAL ----
if mode.startswith("Style"):
    st.markdown("### 🎨 Style Your Original")
    # SAFE default indexes (no post-creation assignment to session_state keys)
    style_options = list(STYLE_PRESETS.keys())
    default_style_index = 0
    style_choice = st.selectbox("Choose a style preset", style_options, index=default_style_index, key="style_original")
    theme_choice = st.selectbox("PNG Theme", ["Dark (punchy)", "Light (clean)"], index=0, key="theme_original")

    if st.session_state.orig_prompt.strip():
        styled = format_prompt_for_style(st.session_state.orig_prompt, style_choice)
        viral_styled = virality_rating(styled)

        st.markdown(
            f"""
            <div class='card'>
              <div style='font-weight:800;margin-bottom:6px'>Preview — {style_choice}</div>
              <pre style='white-space:pre-wrap;font-family:inherit;margin:0'>{styled}</pre>
              <div class="metric" style="margin-top:8px;">
                <div class="pill">🧲 Virality (styled): <b>{viral_styled['score']}%</b> ({viral_styled['label']})</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        copy_box(styled, key="orig_copy", note="Copy-ready prompt")
        bg = "#0f172a" if theme_choice.startswith("Dark") else "#ffffff"
        fg = "#f8fafc" if theme_choice.startswith("Dark") else "#111111"
        png_bytes = render_tile_png(styled, bg=bg, fg=fg, title_emoji="")
        st.download_button("📄 Download TXT", data=styled,
                           file_name=f"styled_{style_choice.replace(' ','_').lower()}.txt", mime="text/plain")
        st.download_button("🖼️ Download PNG Tile", data=png_bytes,
                           file_name=f"styled_{style_choice.replace(' ','_').lower()}.png", mime="image/png")

# ---- RECODE THEN STYLE ----
else:
    n_variants = 4 if include_comedy else 3
    if st.button("Recode it ✨", type="primary", key="recode_btn"):
        if not st.session_state.orig_prompt.strip():
            st.error("Please paste a prompt or topic.")
        else:
            with st.spinner("Generating alternatives…"):
                recs = generate_recodes(st.session_state.orig_prompt, n_variants=n_variants)
            st.session_state.recodes = recs
            st.session_state.pack = {
                "original": {"text": st.session_state.orig_prompt,
                             "scores": st.session_state.orig_scores,
                             "virality": st.session_state.orig_viral},
                "alternatives": []
            }
            st.session_state.generated = True

    if st.session_state.generated and st.session_state.recodes:
        st.markdown("### ✨ Alternatives (pick a style, copy, export)")
        style_options = list(STYLE_PRESETS.keys())

        for idx, rec in enumerate(st.session_state.recodes):
            now = analyze_text(rec["text"])
            tox_drop = max(0, st.session_state.orig_scores['toxicity'] - now['toxicity'])
            dis_drop = max(0, st.session_state.orig_scores['disruption'] - now['disruption'])
            pos_gain = max(0, now['positivity'] - st.session_state.orig_scores['positivity'])
            viral = virality_rating(rec["text"], tox=now["toxicity"], dis=now["disruption"])

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
                    <div class="pill">🧲 Virality: <b>{viral['score']}%</b> ({viral['label']})</div>
                  </div>
                  <div style="margin-top:6px; font-size:14px; opacity:.9;">
                    <b>Why:</b> {" • ".join(viral['reasons'])}
                  </div>
                  <div class="metric" style="margin-top:8px;">
                    <div class="pill">✅ Toxicity reduced: <b>{fmt_delta(tox_drop)}</b></div>
                    <div class="pill">✅ Disruption reduced: <b>{fmt_delta(dis_drop)}</b></div>
                    <div class="pill">✅ Positivity increased: <b>{fmt_delta(pos_gain)}</b></div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            # SAFE defaults for widgets — no manual session_state writes after creation
            style_default_index = 0
            theme_default_index = 0
            style_key = f"style_{idx}"
            theme_key = f"theme_{idx}"

            style_choice = st.selectbox(
                f"Style for: {rec['style']}",
                style_options,
                index=style_default_index,
                key=style_key
            )
            theme_choice = st.selectbox(
                "PNG Theme",
                ["Dark (punchy)", "Light (clean)"],
                index=theme_default_index,
                key=theme_key
            )

            styled_text = format_prompt_for_style(rec["text"], style_choice)
            viral_styled = virality_rating(styled_text)

            st.markdown(
                f"""
                <div class='card' style='background:#fff;border:1px dashed #ccc;'>
                  <div style='font-weight:800;margin-bottom:6px'>Preview — {style_choice}</div>
                  <pre style='white-space:pre-wrap;font-family:inherit;margin:0'>{styled_text}</pre>
                  <div class="metric" style="margin-top:8px;">
                    <div class="pill">🧲 Virality (styled): <b>{viral_styled['score']}%</b> ({viral_styled['label']})</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            copy_box(styled_text, key=f"copy_{idx}", note="Copy-ready prompt")

            bg = "#0f172a" if theme_choice.startswith("Dark") else "#ffffff"
            fg = "#f8fafc" if theme_choice.startswith("Dark") else "#111111"
            png_bytes = render_tile_png(styled_text, bg=bg, fg=fg, title_emoji="")
            st.download_button("📄 Download TXT", data=styled_text,
                               file_name=f"{rec['style'].replace(' ','_').lower()}_{style_choice.replace(' ','_').lower()}.txt",
                               mime="text/plain", key=f"txt_{idx}")
            st.download_button("🖼️ Download PNG Tile", data=png_bytes,
                               file_name=f"{rec['style'].replace(' ','_').lower()}_{style_choice.replace(' ','_').lower()}.png",
                               mime="image/png", key=f"png_{idx}")

        # Pack (optional JSON)
        pack = {
            "original": {"text": st.session_state.orig_prompt,
                         "scores": st.session_state.orig_scores,
                         "virality": st.session_state.orig_viral},
            "alternatives": []
        }
        for idx, rec in enumerate(st.session_state.recodes):
            chosen_style = st.session_state.get(f"style_{idx}", list(STYLE_PRESETS.keys())[0])
            styled_text = format_prompt_for_style(rec["text"], chosen_style)
            pack["alternatives"].append({
                "style": rec["style"],
                "emoji": EMOJI_MAP.get(rec["style"], rec["emoji"]),
                "raw_text": rec["text"],
                "styled_choice": chosen_style,
                "styled_text": styled_text,
                "scores": analyze_text(rec["text"]),
                "virality": virality_rating(rec["text"]),
                "virality_styled": virality_rating(styled_text)
            })

        st.download_button(
            "⬇️ Download JSON pack",
            data=json.dumps(pack, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="prompt_recode_pack.json",
            mime="application/json",
            key="pack_dl"
        )

st.markdown("---")
st.caption("© 2025 Prompt Styler + Recode 4.0 — Pro")
