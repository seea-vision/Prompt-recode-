# seeavision_prompt_recode_pro.py
# -------------------------------------------------------------------
# Prompt Recode 4.0 — Pro Edition (single-file Streamlit app)
#
# Upgrades:
#   • Rates the ORIGINAL prompt first (Disruption, Toxicity, Positivity)
#   • Generates multiple ALTERNATIVES (Serious, Collaborative, Comedic, Uplifting)
#   • Formats each alternative with bold headers + emojis for easy copy/paste
#   • Shows per-alternative IMPROVEMENT METRICS:
#         - Toxicity reduction %
#         - Disruption reduction %
#         - Positivity increase %
#   • Auto-matches output length to input unless user says "shorten/expand"
#   • High-contrast, white background UI (mobile friendly)
#
# Quickstart:
#   pip install streamlit openai
#   export OPENAI_API_KEY=your_key
#   streamlit run seeavision_prompt_recode_pro.py
# -------------------------------------------------------------------

import os, re, json
from typing import List, Dict, Any
import streamlit as st
from openai import OpenAI

# -----------------------------
# OpenAI Setup
# -----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# -----------------------------
# Page / Global Styles (visibility fixes)
# -----------------------------
st.set_page_config(page_title="Prompt Recode 4.0 — Pro", page_icon="✨", layout="wide")

st.markdown("""
<style>
/* Global */
body, .stApp { background:#ffffff !important; color:#111 !important; font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
h1,h2,h3,h4 { color:#2b2b6e; font-weight:700; }
hr { border:none; height:1px; background:#eee; margin:16px 0; }

/* Inputs */
.stTextArea textarea, .stTextInput input {
  background:#fff !important; color:#111 !important; border:1px solid #d9d9d9 !important; border-radius:12px !important; font-size:16px !important;
}
.stTextArea textarea::placeholder { color:#777 !important; }

/* Buttons */
.stButton>button {
  background:#f5c518 !important; color:#111 !important; border:none !important; border-radius:12px !important; font-weight:700 !important;
  padding:0.65em 1.2em; box-shadow:0 2px 5px rgba(0,0,0,0.08);
}
.stButton>button:hover { background:#ffd84d !important; }

/* Cards */
.card {
  background:#fafafa; border:1px solid #eee; border-radius:14px; padding:14px 16px; box-shadow:0 2px 4px rgba(0,0,0,0.04); margin-bottom:12px;
}
.metric { display:flex; gap:10px; flex-wrap:wrap; }
.metric .pill {
  background:#fff; border:1px solid #eee; border-radius:999px; padding:6px 12px; font-weight:600; box-shadow:0 1px 2px rgba(0,0,0,0.03);
}

/* Alert (errors) */
.stAlert { background:#ffecec !important; border:1px solid #f5b5b5 !important; border-radius:12px !important; }
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Lightweight analyzer (heuristics)
# -----------------------------
TOXIC_WORDS = {
    "hate","stupid","idiot","disgusting","trash","fake","owe","jealous",
    "disrespect","loser","dumb","evil","attack","fraud"
}
DISRUPT_WORDS = {"vs","versus","against","beef","war","takedown","clapback","exposed","owe","fake","divide","enemy"}

def analyze_text(text: str) -> Dict[str, int]:
    """Return simple 0-100 scores for toxicity/disruption and a positivity proxy."""
    t = text.lower()
    # counts scaled roughly
    tox_hits = sum(1 for w in TOXIC_WORDS if re.search(rf"\b{re.escape(w)}\b", t))
    dis_hits = sum(1 for w in DISRUPT_WORDS if re.search(rf"\b{re.escape(w)}\b", t))
    exclam = t.count("!")
    caps_ratio = sum(1 for c in text if c.isupper()) / max(1, sum(1 for c in text if c.isalpha()))
    toxicity = int(min(100, tox_hits*12 + exclam*3 + caps_ratio*20))
    disruption = int(min(100, dis_hits*10 + caps_ratio*10))
    positivity = int(max(0, 100 - toxicity))  # simple complement
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

# -----------------------------
# Recode via OpenAI (JSON-structured)
# -----------------------------
def generate_recodes(original: str, n_variants: int = 4) -> List[Dict[str,str]]:
    """
    Returns a list of dicts: [{style, emoji, text}]
    Styles we aim for: Serious, Collaborative Debate, Comedic, Uplifting
    Auto-match length to input unless "shorten/expand" is present.
    """
    if not client:
        st.error("Missing `OPENAI_API_KEY`. Add it to your environment (Render → Environment) and redeploy.")
        st.stop()

    input_len = len(original)
    target_len = input_len
    if re.search(r"\b(short|shorten|condense)\b", original.lower()):
        target_len = max(200, int(input_len*0.6))
    elif re.search(r"\b(long|expand|detailed|thread)\b", original.lower()):
        target_len = int(input_len*1.5)

    system = f"""
You are "Prompt Recode 4.0 — Pro".
Recode an input prompt into multiple aligned alternatives that keep the topic but remove hostility and confusion.

Rules:
- Keep the cultural voice; do NOT punch down.
- Auto-match output length to the input (~{target_len} chars) unless the input says to shorten/expand.
- Output JSON ONLY: a list of objects with keys: style, emoji, text.
- Use these styles at least once: "Serious & Balanced", "Collaborative Debate", "Comedic Spin", "Uplifting Alternative".
- Each 'text' must be a single paragraph suitable for copy/paste.
"""
    user = f"Original prompt:\n{original}\n\nReturn JSON list with 4–6 alternatives."

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            temperature=0.7,
            max_tokens=max(1200, target_len*2)
        )
        content = resp.choices[0].message.content.strip()
    except Exception:
        st.error("Authentication failed. Check your `OPENAI_API_KEY` value.")
        st.stop()

    # Parse JSON robustly
    try:
        data = json.loads(content)
        # Basic sanitation
        out = []
        for item in data:
            style = str(item.get("style","Recode")).strip()
            emoji = str(item.get("emoji","✨")).strip()
            text  = str(item.get("text","")).strip()
            if text:
                out.append({"style":style, "emoji":emoji, "text":text})
        return out[:6] if out else []
    except Exception:
        # Fallback: make one generic variant if JSON parsing failed
        return [{"style":"Recode","emoji":"✨","text":content}]

# -----------------------------
# UI
# -----------------------------
st.title("✨ Prompt Recode 4.0 — Pro")
st.caption("Rate the heat first, then get serious + collaborative + comedic + uplifting alternatives you can copy/paste.")

user_prompt = st.text_area("Paste a prompt/topic", height=180, placeholder="e.g. Why do X act like Y owes them something?")

left, right = st.columns([1,1])

with left:
    st.markdown("#### Options")
    want_comedic = st.checkbox("Include a playful/comedic alternative", value=True)
    n_variants = 4 if want_comedic else 3

if st.button("Recode it ✨", type="primary"):
    if not user_prompt.strip():
        st.error("Please paste a prompt or topic.")
        st.stop()

    # 1) Analyze original
    orig_scores = analyze_text(user_prompt)

    st.markdown("### 🔍 Original Analysis")
    with st.container():
        st.markdown(
            f"""
            <div class="card">
              <div class="metric">
                <div class="pill">⚠️ Toxicity: <b>{orig_scores['toxicity']}%</b></div>
                <div class="pill">🔥 Disruption: <b>{orig_scores['disruption']}%</b></div>
                <div class="pill">🌱 Positivity Potential: <b>{orig_scores['positivity']}%</b></div>
                <div class="pill">🔠 Length: <b>{orig_scores['length']}</b> chars</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # 2) Generate recodes
    with st.spinner("Generating alternatives…"):
        variants = generate_recodes(user_prompt, n_variants=n_variants)

    # 3) Show alternatives with per-variant improvements
    st.markdown("### ✨ Alternatives")
    for i, v in enumerate(variants, start=1):
        rec_scores = analyze_text(v["text"])
        gains = improvement(orig_scores, rec_scores)

        st.markdown(
            f"""
            <div class="card">
              <div style="font-size:18px; font-weight:800; margin-bottom:6px;">
                {v['emoji']} <b>{v['style']}</b>
              </div>
              <div style="white-space:pre-wrap; line-height:1.45; margin:6px 0 10px 0;">
                {v['text']}
              </div>
              <div class="metric">
                <div class="pill">⚠️ Toxicity now: <b>{rec_scores['toxicity']}%</b></div>
                <div class="pill">🔥 Disruption now: <b>{rec_scores['disruption']}%</b></div>
                <div class="pill">🌱 Positivity now: <b>{rec_scores['positivity']}%</b></div>
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

    # 4) Side-by-side copy boxes
    st.markdown("### 📋 Copy & Compare")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Original**")
        st.text_area("Original", user_prompt, height=180, label_visibility="collapsed")
    with col2:
        st.markdown("**Best Alternative (top item)**")
        top_text = variants[0]["text"] if variants else ""
        st.text_area("Recoded", top_text, height=180, label_visibility="collapsed")

    # 5) Download pack
    pack = {
        "original": {"text": user_prompt, "scores": orig_scores},
        "alternatives": [
            {"style": v["style"], "emoji": v["emoji"], "text": v["text"],
             "scores": analyze_text(v["text"]), "improvements": improvement(orig_scores, analyze_text(v["text"]))}
            for v in variants
        ]
    }
    st.download_button("⬇️ Download JSON pack", data=json.dumps(pack, ensure_ascii=False, indent=2).encode("utf-8"),
                       file_name="prompt_recode_pack.json", mime="application/json")

# Footer
st.markdown("---")
st.caption("© 2025 Prompt Recode 4.0 — Pro")
