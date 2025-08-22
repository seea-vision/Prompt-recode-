# seeavision_prompt_recode_app.py
# ------------------------------------------------------------
# SeeAVision "Prompt Recode 4.0" — Modern UI + Batch Mode
#
# What it does
#   • Analyzes a prompt/topic for negativity, toxicity, hype, clarity
#   • Rewrites it into viral-ready, collaborative, funny, and aligned variants
#   • Auto-matches output length to input length (short → short, long → long)
#   • Only shortens/expands when the input explicitly asks to
#   • Batch mode: paste multiple prompts, get a full recoded pack + export JSON/CSV
#
# Run:
#   pip install streamlit openai
#   export OPENAI_API_KEY=your_key_here
#   streamlit run seeavision_prompt_recode_app.py
#
# License: MIT
# ------------------------------------------------------------

import os
import re
import csv
import io
import json
from typing import List, Dict, Any
import streamlit as st
from openai import OpenAI

# ---------------------------
# OpenAI Client
# ---------------------------
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ---------------------------
# Lexicons for heuristic analysis
# ---------------------------
OUTRAGE = {"idiot","stupid","moron","loser","garbage","trash","humiliate","destroyed","obliterated",
           "owned","cringe","pathetic","witchhunt","boycott","cancel","traitor","enemy","fraud",
           "evil","fake","liar","hate","disgusting","dumb"}
DEHUMAN = {"vermin","animals","rats","roaches","subhuman","plague","infestation","thugs"}
HYPE = {"shocking","insane","unbelievable","you won’t believe","must see","epic takedown",
        "exposed","BREAKING","ALL CAPS","THIS CHANGES EVERYTHING","ultimate","mind-blowing"}
CONFLICT = {"vs","debunk","exposed","takedown","clapback","feud","beef","war","fight","destroy"}
POSITIVE = {"clarity","learn","questions","together","perspective","listen","curious","build",
            "practice","skill","peace","fun","try","experiment","guide","how to","steps",
            "co-create","community","repair","respect","collaborate","share"}

# ---------------------------
# Heuristic analyzers
# ---------------------------
def _tok(s: str) -> List[str]:
    return re.findall(r"[A-Za-z']+", s.lower())

def _cap_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if not letters: return 0.0
    return sum(1 for c in letters if c.isupper())/len(letters)

def _contains_any(s: str, vocab: set[str]) -> int:
    T = s.lower()
    return sum(1 for w in vocab if w in T)

def _exclaim_ratio(s: str) -> float:
    return min(s.count("!")/max(1,len(s)), 1.0)

def analyze_prompt(p: str) -> Dict[str, Any]:
    tokens = _tok(p)
    length = max(1, len(tokens))
    o = _contains_any(p, OUTRAGE) + sum(1 for t in tokens if t in OUTRAGE)
    d = _contains_any(p, DEHUMAN) + sum(1 for t in tokens if t in DEHUMAN)
    h = _contains_any(p, HYPE) + sum(1 for t in tokens if t in HYPE)
    c = _contains_any(p, CONFLICT) + sum(1 for t in tokens if t in CONFLICT)
    pos = _contains_any(p, POSITIVE) + sum(1 for t in tokens if t in POSITIVE)
    caps = _cap_ratio(p)
    exr = _exclaim_ratio(p)

    negativity = min(1.0, (o*0.6 + c*0.4)/max(6, length/6))
    toxicity = min(1.0, (o*0.5 + d*1.0 + caps*2 + exr*1.2))
    hype = min(1.0, (h*0.6 + caps*0.7 + exr*0.4))
    clarity = max(0.0, 1.0 - (hype*0.35 + toxicity*0.4 + negativity*0.25)) * (0.6 + min(pos/6, 0.4))

    return {
        "negativity": round(negativity,3),
        "toxicity": round(toxicity,3),
        "hype": round(hype,3),
        "clarity": round(clarity,3),
        "caps_ratio": round(caps,3),
        "exclaim_ratio": round(exr,3),
        "len_tokens": len(tokens),
        "input_chars": len(p),
    }

# ---------------------------
# Prompt Recode 4.0 Functionality
# ---------------------------
def recode_prompt_40(
    topic: str,
    virality: float = 0.55,
    humor: float = 0.45,
    debate_heat: float = 0.40,
    safety: float = 0.70,
    num_variants: int = 6
) -> Dict[str, Any]:
    """Generate rewrites that auto-match input length unless instructed otherwise."""
    analysis = analyze_prompt(topic)
    input_length = len(topic)

    # Default cap = length of input
    target_length = input_length

    # If user explicitly says "shorten" or "expand", adjust target length
    if re.search(r"\b(short|shorten|condense)\b", topic.lower()):
        target_length = max(200, int(input_length * 0.5))
    elif re.search(r"\b(long|expand|detailed|thread)\b", topic.lower()):
        target_length = int(input_length * 1.5)

    system_prompt = f"""
You are a cultural decoder and prompt transformer trained in "Prompt Recode 4.0".
You upgrade destructive or confusing prompts into viral-ready, collaborative, funny,
and clear discussions.

Guidelines:
- Keep voice, slang, and energy unless directly harmful.
- Flip FUNCTION from outrage/fear → clarity, collaboration, curiosity.
- Never sanitize identity—keep bold.
- Aim for visibility (hooks, cadence) without division or harm.

Output exactly {num_variants} rewrites, each labeled with one style:
[Collaborative, Curious Debate, Light-Hearted, Story-First, Solution/How-To, Peace-Viral Challenge].
Each rewrite should be roughly the same length as the input (~{target_length} characters),
unless the input explicitly asked you to shorten or expand.

Sliders (do not echo values; interpret them):
- Virality (spice level): {virality:.2f}
- Humor (playfulness): {humor:.2f}
- Debate heat (kind, not cruel): {debate_heat:.2f}
- Safety strictness (de-escalation): {safety:.2f}
""".strip()

    user_prompt = f"Original prompt/topic:\n{topic}\n\nRewrite now."

    if not client:
        return {"error": "Missing OPENAI_API_KEY", "variants": [], "analysis": analysis}

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_prompt}],
        temperature=0.7,
        max_tokens=max(1200, int(target_length*2))  # allow enough room for longer threads
    )
    content = resp.choices[0].message.content.strip()

    # Parse
    lines = [l.strip(" -•\t") for l in content.splitlines() if l.strip()]
    variants = []
    for ln in lines:
        m = re.match(r"(Collaborative|Curious Debate|Light-Hearted|Story-First|Solution/How-To|Peace-Viral Challenge)\s*:\s*(.+)", ln, flags=re.I)
        if m:
            variants.append({"style": m.group(1).strip(), "text": m.group(2).strip()})
    if not variants:
        variants = [{"style": "Recode", "text": ln} for ln in lines][:num_variants]

    # Trim any wildly long outliers (> 1.5x target) while respecting user "expand"
    hard_max = int(target_length * (1.5 if re.search(r"\b(long|expand|detailed|thread)\b", topic.lower()) else 1.1)) + 40
    for v in variants:
        if len(v["text"]) > hard_max:
            v["text"] = v["text"][:hard_max].rstrip()

    return {"analysis": analysis, "variants": variants[:num_variants]}

# ---------------------------
# UI Helpers
# ---------------------------
def build_csv(rows: List[Dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["index","original","style","rewrite","negativity","toxicity","hype","clarity","length_in","length_out"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")

# ---------------------------
# Streamlit UI + Styling
# ---------------------------
st.set_page_config(page_title="Prompt Recode 4.0", layout="wide")
st.title("🔄 Prompt Recode 4.0")
st.caption("Flip spicy prompts into viral, collaborative, and funny discussions — without destruction.")

# --- Custom CSS for Modern Look (white background, indigo headers, gold buttons, card tiles) ---
st.markdown("""
    <style>
    body { background-color: #ffffff; color: #1a1a1a; }
    .stApp { background-color: #ffffff; font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
    h1, h2, h3, h4 { font-weight: 600; color: #2b2b6e; }
    .stButton>button {
        background-color: #f5c518;
        color: #1a1a1a;
        font-weight: 600;
        border-radius: 12px;
        padding: 0.6em 1.2em;
        box-shadow: 0px 2px 5px rgba(0,0,0,0.1);
        border: none;
    }
    .stButton>button:hover { background-color: #ffd84d; color: black; }
    .stTextArea textarea, .stTextInput input {
        border-radius: 12px; border: 1px solid #ddd;
    }
    .prompt-box {
        background-color: #fafafa;
        border: 1px solid #eee;
        border-radius: 12px;
        padding: 1em;
        margin-bottom: 1em;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .metric-card {
        background: #fff;
        border: 1px solid #eee;
        border-radius: 12px;
        padding: 0.8em 1em;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar controls
with st.sidebar:
    st.header("Tuning")
    virality = st.slider("Virality spice", 0.0, 1.0, 0.55, 0.01)
    humor = st.slider("Humor", 0.0, 1.0, 0.45, 0.01)
    debate = st.slider("Debate Heat", 0.0, 1.0, 0.40, 0.01)
    safety = st.slider("Safety Strictness", 0.0, 1.0, 0.70, 0.01)
    nvars = st.selectbox("Rewrites per prompt", [3,4,5,6], index=3)

    st.divider()
    st.header("Mode")
    batch_mode = st.toggle("Batch mode (multiple prompts)")

# ---------------------------
# Inputs
# ---------------------------
if not batch_mode:
    st.markdown("### Paste a prompt/topic")
    default = "Every influencer is fake!!!"
    text = st.text_area("Prompt", value=default, height=170)

    if st.button("Recode it ✨"):
        if not text.strip():
            st.error("Please paste a prompt or topic.")
        else:
            with st.spinner("Recoding..."):
                out = recode_prompt_40(text, virality, humor, debate, safety, int(nvars))
            if "error" in out:
                st.error(out["error"])
            else:
                # Metrics
                st.subheader("📊 Analysis")
                a = out["analysis"]
                c1, c2, c3, c4 = st.columns(4)
                with c1: st.markdown(f"<div class='metric-card'><b>Negativity</b><br>{a['negativity']}</div>", unsafe_allow_html=True)
                with c2: st.markdown(f"<div class='metric-card'><b>Toxicity</b><br>{a['toxicity']}</div>", unsafe_allow_html=True)
                with c3: st.markdown(f"<div class='metric-card'><b>Hype</b><br>{a['hype']}</div>", unsafe_allow_html=True)
                with c4: st.markdown(f"<div class='metric-card'><b>Clarity</b><br>{a['clarity']}</div>", unsafe_allow_html=True)
                st.caption(f"Input length: {a['input_chars']} chars")

                # Variants
                st.subheader("✨ Variants")
                for v in out["variants"]:
                    st.markdown(
                        f"""
                        <div class="prompt-box">
                            <strong>{v['style']}</strong><br>
                            {v['text']}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
else:
    st.markdown("### Paste prompts (one per line)")
    default_batch = "Politics vs. friendship — pick a side\nThe gym is a scam\nAre landlords evil or necessary?\nEvery influencer is fake!!!"
    batch_text = st.text_area("Prompts", value=default_batch, height=220, help="One prompt/topic per line. Rewrites will auto-match each line’s length.")

    if st.button("Recode them all ✨"):
        prompts = [p.strip() for p in batch_text.splitlines() if p.strip()]
        if not prompts:
            st.error("Please paste at least one prompt.")
        else:
            rows_for_csv: List[Dict[str, Any]] = []
            pack: List[Dict[str, Any]] = []
            tabs = st.tabs([f"Item {i+1}" for i in range(len(prompts))])

            for idx, (tab, prompt) in enumerate(zip(tabs, prompts)):
                with tab:
                    with st.spinner(f"Recoding item {idx+1}…"):
                        out = recode_prompt_40(prompt, virality, humor, debate, safety, int(nvars))
                    if "error" in out:
                        st.error(out["error"])
                        continue

                    a = out["analysis"]
                    st.markdown(f"**Original:**\n\n> {prompt}")
                    c1, c2, c3, c4 = st.columns(4)
                    with c1: st.markdown(f"<div class='metric-card'><b>Negativity</b><br>{a['negativity']}</div>", unsafe_allow_html=True)
                    with c2: st.markdown(f"<div class='metric-card'><b>Toxicity</b><br>{a['toxicity']}</div>", unsafe_allow_html=True)
                    with c3: st.markdown(f"<div class='metric-card'><b>Hype</b><br>{a['hype']}</div>", unsafe_allow_html=True)
                    with c4: st.markdown(f"<div class='metric-card'><b>Clarity</b><br>{a['clarity']}</div>", unsafe_allow_html=True)
                    st.caption(f"Input length: {a['input_chars']} chars")

                    st.subheader("✨ Variants")
                    for v in out["variants"]:
                        st.markdown(
                            f"""
                            <div class="prompt-box">
                                <strong>{v['style']}</strong><br>
                                {v['text']}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        rows_for_csv.append({
                            "index": idx+1,
                            "original": prompt,
                            "style": v["style"],
                            "rewrite": v["text"],
                            "negativity": a["negativity"],
                            "toxicity": a["toxicity"],
                            "hype": a["hype"],
                            "clarity": a["clarity"],
                            "length_in": a["input_chars"],
                            "length_out": len(v["text"]),
                        })
                    pack.append({
                        "index": idx+1,
                        "original": prompt,
                        "analysis": a,
                        "rewrites": out["variants"]
                    })

            # Exports
            st.subheader("📦 Export")
            json_bytes = json.dumps(pack, ensure_ascii=False, indent=2).encode("utf-8")
            st.download_button("⬇️ Download JSON pack", data=json_bytes, file_name="prompt_recode_pack.json", mime="application/json")

            csv_bytes = build_csv(rows_for_csv)
            st.download_button("⬇️ Download CSV (for sheets/calendars)", data=csv_bytes, file_name="prompt_recode_pack.csv", mime="text/csv")
