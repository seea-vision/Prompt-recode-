import os
import streamlit as st
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# -----------------------------
# Streamlit Page Config
# -----------------------------
st.set_page_config(page_title="Prompt Recode 4.0", layout="wide", page_icon="✨")

# -----------------------------
# Custom Styling (visibility fix)
# -----------------------------
st.markdown("""
<style>
/* Global background and text */
body, .stApp {
  background: #ffffff !important;
  color: #111111 !important;
  font-family: "Inter", "Segoe UI", sans-serif;
}

/* Input fields */
.stTextArea textarea, .stTextInput input {
  background: #ffffff !important;
  color: #111111 !important;
  border: 1px solid #d9d9d9 !important;
  border-radius: 12px !important;
  font-size: 16px !important;
}
.stTextArea textarea::placeholder {
  color: #777777 !important;
}

/* Buttons */
.stButton > button {
  background: #f5c518 !important;
  color: #111111 !important;
  border-radius: 12px !important;
  border: none !important;
  font-weight: 600 !important;
  padding: 0.6em 1.2em;
}
.stButton > button:hover {
  background: #ffdb4d !important;
  color: #000000 !important;
}

/* Alert styling */
.stAlert, .stAlert p, .stAlert div {
  color: #111111 !important;
}
.stAlert {
  background: #ffecec !important;
  border: 1px solid #f5b5b5 !important;
  border-radius: 12px !important;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Recode Function
# -----------------------------
def recode_prompt(user_prompt: str, target_length: int = None) -> str:
    """
    Recode a prompt into collaborative, viral-ready text.
    Maintains input length unless shortening is requested.
    """
    system_prompt = """You are Prompt Recode 4.0 — a cultural transformer.
You rewrite prompts and topics into collaborative, funny, viral-ready rewrites.
Rules:
- Keep the same length as the input unless user requests shortening.
- Remove destructive negativity while preserving energy and style.
- Encourage debate, humor, and lightness instead of hostility.
- Keep tone bold, not sanitized."""

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=max(1200, len(user_prompt) * 2)
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        st.error("⚠️ Authentication failed. Check your `OPENAI_API_KEY` in Render → Environment and redeploy.")
        st.caption("Tip: Name must be exactly `OPENAI_API_KEY` and the value should start with `sk-`.")
        st.stop()

# -----------------------------
# Streamlit UI
# -----------------------------
st.title("✨ Prompt Recode 4.0")
st.subheader("Flip spicy prompts into viral, collaborative, and funny discussions — without destruction.")

user_prompt = st.text_area("Paste a prompt/topic", height=180, placeholder="e.g. Every influencer is fake!!!")

if st.button("Recode it ✨", type="primary") and user_prompt:
    with st.spinner("Rewriting with Prompt Recode 4.0..."):
        recoded = recode_prompt(user_prompt)
        st.success("✅ Recode complete!")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Original")
            st.text_area("Original Prompt", user_prompt, height=250, label_visibility="collapsed")
        with col2:
            st.markdown("#### Recoded")
            st.text_area("Recoded Prompt", recoded, height=250, label_visibility="collapsed")

        # Download button
        st.download_button(
            label="📥 Download Recoded Prompt",
            data=recoded,
            file_name="recoded_prompt.txt",
            mime="text/plain"
        )

st.markdown("---")
st.caption("© 2025 Prompt Recode 4.0 | SeeeaVision")
