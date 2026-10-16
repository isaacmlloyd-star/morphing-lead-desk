import os
import json
import urllib.parse
import streamlit as st
from PIL import Image
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# PAGE CONFIG & SCI-FI DARK HUD STYLING
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Morphing B2B Lead Desk",
    page_icon="⚡",
    layout="wide",
)

st.markdown("""
<style>
    .stApp { background-color: #0b0f19; color: #e2e8f0; }
    .mode-banner {
        padding: 14px 20px;
        border-radius: 10px;
        background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%);
        border-left: 5px solid #38bdf8;
        margin-bottom: 20px;
    }
    .pass-badge { background-color: #065f46; color: #34d399; padding: 4px 10px; border-radius: 6px; font-weight: bold; }
    .revise-badge { background-color: #78350f; color: #fbbf24; padding: 4px 10px; border-radius: 6px; font-weight: bold; }
    .hold-badge { background-color: #7f1d1d; color: #f87171; padding: 4px 10px; border-radius: 6px; font-weight: bold; }
    .card-box {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 14px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# ---------------------------------------------------------------------------
if "ui_mode" not in st.session_state:
    st.session_state.ui_mode = "MODE_1_SCANNER"
if "batch_id" not in st.session_state:
    st.session_state.batch_id = "BATCH-001"
if "niche" not in st.session_state:
    st.session_state.niche = "Commercial Solar Installers"
if "city" not in st.session_state:
    st.session_state.city = "Midrand & Johannesburg"
if "offer" not in st.session_state:
    st.session_state.offer = "a free 15-minute call showing our automated weekly commercial lead desk that delivers 10 qualified B2B enquiries every Monday"
if "sender" not in st.session_state:
    st.session_state.sender = "Isaac from Apex Agent Systems"
if "leads" not in st.session_state:
    st.session_state.leads = []
if "drafts" not in st.session_state:
    st.session_state.drafts = []
if "reviews" not in st.session_state:
    st.session_state.reviews = []
if "approvals" not in st.session_state:
    st.session_state.approvals = {}

# ---------------------------------------------------------------------------
# SIDEBAR: API KEY & SETTINGS
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚡ Agent Command")
    
    secret_key = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            secret_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

    api_key_input = st.text_input(
        "Gemini API Key (Free Tier)",
        value=secret_key or os.environ.get("GEMINI_API_KEY", ""),
        type="password",
        help="Get your free key at aistudio.google.com/app/apikey"
    )
    if api_key_input:
        os.environ["GEMINI_API_KEY"] = api_key_input

    st.divider()
    st.subheader("🔄 Active Morph State")
    mode_labels = {
        "MODE_1_SCANNER": "1. Field Scanner & Radar",
        "MODE_2_RESEARCH": "2. @Researcher Table",
        "MODE_3_AUDIT": "3. @Writer + @Reviewer Audit",
        "MODE_4_CLIENT_DECK": "4. Monday Client Approval Deck",
    }
    selected_mode = st.radio(
        "Morph UI Into:",
        options=list(mode_labels.keys()),
        format_func=lambda x: mode_labels[x],
        index=list(mode_labels.keys()).index(st.session_state.ui_mode)
    )
    if selected_mode != st.session_state.ui_mode:
        st.session_state.ui_mode = selected_mode
        st.rerun()

def get_client():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        st.error("Please enter your free Gemini API Key in the sidebar or Streamlit Secrets!")
        st.stop()
    return genai.Client(api_key=key)

# ---------------------------------------------------------------------------
# THE 3 AGENT BRAINS (Guaranteed Stable Execution)
# ---------------------------------------------------------------------------
def run_vision_extractor(image_file):
    client = get_client()
    img = Image.open(image_file)
    prompt = "Extract the business type/niche, city/location, and company names from this image. Return ONLY valid JSON with keys: niche, city, notes."
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[img, prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return json.loads(resp.text)

def run_researcher_agent(batch_id, niche, city, count=3):
    client = get_client()
    prompt = f"""
    You are @Researcher in #lead-desk. Start {batch_id}.
    Provide exactly {count} realistic, independently operated {niche} in {city}.
    STRICT RULES:
    - Return ONLY a valid JSON list of objects with these exact keys:
    [
      {{
        "lead_number": 1,
        "business_name": "...",
        "city": "...",
        "website_or_source_url": "https://...",
        "verified_fact": "...",
        "observed_gap": "...",
        "public_contact": "...",
        "verification_status": "VERIFIED"
      }}
    ]
    """
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    text = resp.text.strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start != -1 and end != 0:
        return json.loads(text[start:end])
    raise ValueError(f"Could not parse Researcher output: {text}")

def run_writer_agent(batch_id, leads_json, offer, sender):
    client = get_client()
    prompt = f"""
    You are @Writer in #lead-desk. Use the Researcher table for {batch_id}:
    {json.dumps(leads_json, indent=2)}

    Write one subject line and one short 60-90 word personalized email per lead.
    Offer: {offer}. Sender: {sender}.
    Return ONLY a valid JSON list with keys: lead_number, business_name, subject, body, word_count.
    """
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    text = resp.text.strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start != -1 and end != 0:
        return json.loads(text[start:end])
    raise ValueError(f"Could not parse Writer output: {text}")

def run_reviewer_agent(batch_id, leads_json, drafts_json):
    client = get_client()
    prompt = f"""
    You are @Reviewer in #lead-desk. Review {batch_id} drafts against sources.
    RESEARCH TABLE: {json.dumps(leads_json, indent=2)}
    WRITER DRAFTS: {json.dumps(drafts_json, indent=2)}

    Label each lead strictly as "PASS", "REVISE", or "HOLD".
    Return ONLY a valid JSON list with keys: lead_number, business_name, verdict, audit_notes, correction_request.
    """
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    text = resp.text.strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start != -1 and end != 0:
        return json.loads(text[start:end])
    raise ValueError(f"Could not parse Reviewer output: {text}")

# ---------------------------------------------------------------------------
# UI ROUTING
# ---------------------------------------------------------------------------
if st.session_state.ui_mode == "MODE_1_SCANNER":
    st.markdown("""
    <div class="mode-banner">
        <h3>📸 MODE 1: Field Scanner & Niche Radar</h3>
        <p>Configure your target niche & city or scan a field card. Clicking below morphs the app into the @Researcher Extraction Grid.</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.session_state.batch_id = st.text_input("Batch ID", st.session_state.batch_id)
        st.session_state.niche = st.text_input("Target Business Type (Niche)", st.session_state.niche)
        st.session_state.city = st.text_input("Target City / Area", st.session_state.city)
        st.session_state.offer = st.text_area("The Offer (for @Writer)", st.session_state.offer)
        st.session_state.sender = st.text_input("Sender Name & Business", st.session_state.sender)
        lead_count = st.slider("Number of Leads in Batch", 3, 10, 3)

        if st.button("🚀 Tag @Researcher & Morph to Extraction Grid", type="primary", use_container_width=True):
            with st.spinner(f"@Researcher is analyzing {st.session_state.niche} in {st.session_state.city}..."):
                st.session_state.leads = run_researcher_agent(
                    st.session_state.batch_id,
                    st.session_state.niche,
                    st.session_state.city,
                    lead_count
                )
                st.session_state.ui_mode = "MODE_2_RESEARCH"
                st.rerun()

    with col2:
        uploaded_img = st.file_uploader("Upload Field Photo / Business Card", type=["png", "jpg", "jpeg"])
        if uploaded_img is not None:
            st.image(uploaded_img, use_container_width=True)
            if st.button("🔍 Extract Target Niche", use_container_width=True):
                with st.spinner("Gemini Vision reading image..."):
                    extracted = run_vision_extractor(uploaded_img)
                    st.session_state.niche = extracted.get("niche", st.session_state.niche)
                    st.session_state.city = extracted.get("city", st.session_state.city)
                    st.success(f"Extracted: {st.session_state.niche} in {st.session_state.city}")
                    st.rerun()

elif st.session_state.ui_mode == "MODE_2_RESEARCH":
    st.markdown(f"""
    <div class="mode-banner">
        <h3>🔎 MODE 2: @Researcher Extraction Grid ({st.session_state.batch_id})</h3>
        <p>Verified public facts and source URLs.</p>
    </div>
    """, unsafe_allow_html=True)

    for lead in st.session_state.leads:
        st.markdown(f"""
        <div class="card-box">
            <h4>Lead #{lead.get('lead_number')}: {lead.get('business_name')} ({lead.get('city')})
                <span class="pass-badge" style="float:right;">{lead.get('verification_status')}</span>
            </h4>
            <p><strong>🔗 Source:</strong> <a href="{lead.get('website_or_source_url')}" target="_blank">{lead.get('website_or_source_url')}</a></p>
            <p><strong>✅ Fact:</strong> {lead.get('verified_fact')}</p>
            <p><strong>🎯 Gap:</strong> {lead.get('observed_gap')}</p>
            <p><strong>📬 Contact:</strong> <code>{lead.get('public_contact')}</code></p>
        </div>
        """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("⬅️ Back to Scanner", use_container_width=True):
            st.session_state.ui_mode = "MODE_1_SCANNER"
            st.rerun()
    with c2:
        if st.button("✍️ Tag @Writer & @Reviewer → Morph to Audit Studio", type="primary", use_container_width=True):
            with st.spinner("Generating drafts & auditing claims..."):
                st.session_state.drafts = run_writer_agent(
                    st.session_state.batch_id,
                    st.session_state.leads,
                    st.session_state.offer,
                    st.session_state.sender
                )
                st.session_state.reviews = run_reviewer_agent(
                    st.session_state.batch_id,
                    st.session_state.leads,
                    st.session_state.drafts
                )
                st.session_state.ui_mode = "MODE_3_AUDIT"
                st.rerun()

elif st.session_state.ui_mode == "MODE_3_AUDIT":
    st.markdown(f"""
    <div class="mode-banner">
        <h3>🛡️ MODE 3: Split-Screen Audit Studio ({st.session_state.batch_id})</h3>
    </div>
    """, unsafe_allow_html=True)

    for idx, draft in enumerate(st.session_state.drafts):
        review = st.session_state.reviews[idx] if idx < len(st.session_state.reviews) else {}
        verdict = review.get("verdict", "PASS").upper()
        badge_class = "pass-badge" if "PASS" in verdict else ("revise-badge" if "REVISE" in verdict else "hold-badge")

        left, right = st.columns([3, 2])
        with left:
            st.markdown(f"""
            <div class="card-box">
                <h4>✉️ Lead #{draft.get('lead_number')}: {draft.get('business_name')}</h4>
                <p><strong>Subject:</strong> {draft.get('subject')}</p>
                <hr style="border-color:#1f2937;">
                <p style="white-space: pre-wrap;">{draft.get('body')}</p>
            </div>
            """, unsafe_allow_html=True)
        with right:
            st.markdown(f"""
            <div class="card-box">
                <h4>🔍 Verdict: <span class="{badge_class}">{verdict}</span></h4>
                <p>{review.get('audit_notes')}</p>
            </div>
            """, unsafe_allow_html=True)

    if st.button("📲 Morph to Client Approval Deck", type="primary", use_container_width=True):
        st.session_state.ui_mode = "MODE_4_CLIENT_DECK"
        st.rerun()

elif st.session_state.ui_mode == "MODE_4_CLIENT_DECK":
    st.markdown(f"""
    <div class="mode-banner">
        <h3>☕ MODE 4: Monday Client Approval Room ({st.session_state.batch_id})</h3>
    </div>
    """, unsafe_allow_html=True)

    for idx, draft in enumerate(st.session_state.drafts):
        lead_num = draft.get("lead_number", idx + 1)
        status = st.session_state.approvals.get(lead_num, "PENDING")

        st.markdown(f"""
        <div class="card-box">
            <h4>{draft.get('business_name')} — <span style="color:#38bdf8;">{status}</span></h4>
            <pre style="background:#0f172a; padding:12px; border-radius:8px; white-space:pre-wrap; color:#f8fafc;">{draft.get('body')}</pre>
        </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            if st.button(f"✅ Approve #{lead_num}", key=f"app_{lead_num}", use_container_width=True):
                st.session_state.approvals[lead_num] = "APPROVED"
                st.rerun()
        with c2:
            if st.session_state.approvals.get(lead_num) == "APPROVED":
                sub = urllib.parse.quote(draft.get("subject", ""))
                body = urllib.parse.quote(draft.get("body", ""))
                st.markdown(f"👉 **[Open in Email Client](mailto:?subject={sub}&body={body})**") 
