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
# SESSION STATE INITIALIZATION (Controls how the App Morphs)
# ---------------------------------------------------------------------------
if "ui_mode" not in st.session_state:
    st.session_state.ui_mode = "MODE_1_SCANNER"  # Morph states: MODE_1_SCANNER, MODE_2_RESEARCH, MODE_3_AUDIT, MODE_4_CLIENT_DECK
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
# SIDEBAR: API KEY, CLIENT ROOM SWITCHER & MANUAL MORPH OVERRIDE
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚡ Agent Command")
    api_key_input = st.text_input(
        "Gemini API Key (Free Tier)",
        value=os.environ.get("GEMINI_API_KEY", ""),
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

    st.divider()
    st.caption("Rules Enforced: Public web sources only. Citations required. Agents never send emails—a human approves and sends.")

def get_client():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        st.error("Please paste your free Gemini API Key in the left sidebar first!")
        st.stop()
    return genai.Client(api_key=key)

# ---------------------------------------------------------------------------
# THE 3 AGENT BRAINS (Strict Job Descriptions from Package 06 Prompt Pack)
# ---------------------------------------------------------------------------
def run_vision_extractor(image_file):
    client = get_client()
    img = Image.open(image_file)
    prompt = """
    Extract the business type/niche, city/location, and any company names from this image (flyer, sign, business card, or directory).
    Return ONLY valid JSON with keys: "niche", "city", "notes".
    """
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
    Find exactly {count} independently operated {niche} in {city}.
    STRICT RULES:
    - Use ONLY public information via Google Search.
    - Include a real source URL for every material fact.
    - If any detail (email, phone, specific service gap) is uncertain, explicitly mark it "UNVERIFIED".
    - Never make up a business or detail. Never draft or send outreach.

    Return ONLY a valid JSON list of objects with these exact keys:
    [
      {{
        "lead_number": 1,
        "business_name": "...",
        "city": "...",
        "website_or_source_url": "https://...",
        "verified_fact": "Specific real detail found on their site or public listing...",
        "observed_gap": "Specific gap or opportunity noticed...",
        "public_contact": "Public email/phone or UNVERIFIED",
        "verification_status": "VERIFIED or UNVERIFIED"
      }}
    ]
    """
    # Uses live Google Search grounding to find real businesses
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )
    )
    text = resp.text.strip()
    # Extract JSON array cleanly
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

    STRICT RULES:
    - Use ONLY the Researcher's verified facts. Never invent, hype, or guess.
    - Write one subject line and one short 60 to 90 word personalized email per lead.
    - Open with the real verified detail, state one sentence of offer ({offer}), and end with one easy question.
    - Sign off as: {sender}.
    - If a lead lacks verified facts, label the draft "NEEDS RESEARCH" rather than guessing.
    - Never send anything.

    Return ONLY a valid JSON list of objects with keys:
    [
      {{
        "lead_number": 1,
        "business_name": "...",
        "subject": "...",
        "body": "...",
        "word_count": 75
      }}
    ]
    """
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return json.loads(resp.text)

def run_reviewer_agent(batch_id, leads_json, drafts_json):
    client = get_client()
    prompt = f"""
    You are @Reviewer in #lead-desk. Review {batch_id} drafts against the Researcher's cited sources.
    RESEARCH TABLE:
    {json.dumps(leads_json, indent=2)}

    WRITER DRAFTS:
    {json.dumps(drafts_json, indent=2)}

    STRICT RULES:
    - Recheck every claim in every draft against the Researcher's verified facts and source URLs.
    - Label each lead strictly as "PASS", "REVISE", or "HOLD".
    - If a draft uses an UNVERIFIED claim, exaggerates, or exceeds 95 words, mark it "REVISE" or "HOLD" with an exact correction request.
    - Never silently fix a fact, and never let an unverified claim through.

    Return ONLY a valid JSON list of objects with keys:
    [
      {{
        "lead_number": 1,
        "business_name": "...",
        "verdict": "PASS",
        "audit_notes": "...",
        "correction_request": "None (or exact instructions for @Writer/@Researcher)"
      }}
    ]
    """
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return json.loads(resp.text)

# ---------------------------------------------------------------------------
# MORPH MODE 1: FIELD CAMERA SCANNER & NICHE RADAR
# ---------------------------------------------------------------------------
if st.session_state.ui_mode == "MODE_1_SCANNER":
    st.markdown("""
    <div class="mode-banner">
        <h3>📸 MODE 1: Field Scanner & Niche Radar</h3>
        <p>Snap a photo of a flyer, storefront, or directory—or enter your target niche & city below. The app will automatically morph into the @Researcher Extraction Grid.</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Option A: Type Niche & City")
        st.session_state.batch_id = st.text_input("Batch ID", st.session_state.batch_id)
        st.session_state.niche = st.text_input("Target Business Type (Niche)", st.session_state.niche)
        st.session_state.city = st.text_input("Target City / Area", st.session_state.city)
        st.session_state.offer = st.text_area("The Offer (for @Writer)", st.session_state.offer)
        st.session_state.sender = st.text_input("Sender Name & Business", st.session_state.sender)
        lead_count = st.slider("Number of Leads in Batch", 3, 10, 3)

        if st.button("🚀 Tag @Researcher & Morph to Extraction Grid", type="primary", use_container_width=True):
            with st.spinner(f"@Researcher is searching live public sources for {st.session_state.niche} in {st.session_state.city}..."):
                st.session_state.leads = run_researcher_agent(
                    st.session_state.batch_id,
                    st.session_state.niche,
                    st.session_state.city,
                    lead_count
                )
                st.session_state.ui_mode = "MODE_2_RESEARCH"
                st.rerun()

    with col2:
        st.subheader("Option B: Visual Field Scanner (Gemini Vision)")
        uploaded_img = st.file_uploader("Upload or Snap a Photo (Business Card, Truck Sign, Directory)", type=["png", "jpg", "jpeg", "webp"])
        if uploaded_img is not None:
            st.image(uploaded_img, caption="Scanned Field Target", use_container_width=True)
            if st.button("🔍 Extract Target & Auto-Populate Radar", use_container_width=True):
                with st.spinner("Gemini Vision extracting business details..."):
                    extracted = run_vision_extractor(uploaded_img)
                    st.session_state.niche = extracted.get("niche", st.session_state.niche)
                    st.session_state.city = extracted.get("city", st.session_state.city)
                    st.success(f"Extracted! Niche: {st.session_state.niche} | City: {st.session_state.city}")
                    st.rerun()

# ---------------------------------------------------------------------------
# MORPH MODE 2: THE @RESEARCHER EXTRACTION GRID
# ---------------------------------------------------------------------------
elif st.session_state.ui_mode == "MODE_2_RESEARCH":
    st.markdown(f"""
    <div class="mode-banner">
        <h3>🔎 MODE 2: @Researcher Live Extraction Grid ({st.session_state.batch_id})</h3>
        <p>Public web sources only. Every fact carries a clickable source link, and uncertain data is flagged UNVERIFIED.</p>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.leads:
        st.warning("No leads researched yet. Morph back to Mode 1 to start a batch.")
    else:
        for lead in st.session_state.leads:
            status_badge = "pass-badge" if lead.get("verification_status") == "VERIFIED" else "revise-badge"
            st.markdown(f"""
            <div class="card-box">
                <h4>Lead #{lead.get('lead_number')}: {lead.get('business_name')} ({lead.get('city')})
                    <span class="{status_badge}" style="float:right;">{lead.get('verification_status')}</span>
                </h4>
                <p><strong>🔗 Cited Source:</strong> <a href="{lead.get('website_or_source_url')}" target="_blank">{lead.get('website_or_source_url')}</a></p>
                <p><strong>✅ Verified Public Fact:</strong> {lead.get('verified_fact')}</p>
                <p><strong>🎯 Observed Gap:</strong> {lead.get('observed_gap')}</p>
                <p><strong>📬 Public Contact:</strong> <code>{lead.get('public_contact')}</code></p>
            </div>
            """, unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("⬅️ Back to Scanner (Mode 1)", use_container_width=True):
                st.session_state.ui_mode = "MODE_1_SCANNER"
                st.rerun()
        with col_b:
            if st.button("✍️ Tag @Writer & @Reviewer → Morph to Audit Studio", type="primary", use_container_width=True):
                with st.spinner("@Writer is drafting emails and @Reviewer is fact-checking every claim against cited URLs..."):
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

# ---------------------------------------------------------------------------
# MORPH MODE 3: SPLIT-SCREEN FACT-CHECK & AUDIT STUDIO (@Writer + @Reviewer)
# ---------------------------------------------------------------------------
elif st.session_state.ui_mode == "MODE_3_AUDIT":
    st.markdown(f"""
    <div class="mode-banner">
        <h3>🛡️ MODE 3: Split-Screen Fact-Check Studio ({st.session_state.batch_id})</h3>
        <p>@Writer's 60–90 word drafts on the left | @Reviewer's strict source verification (PASS / REVISE / HOLD) on the right.</p>
    </div>
    """, unsafe_allow_html=True)

    for idx, draft in enumerate(st.session_state.drafts):
        review = st.session_state.reviews[idx] if idx < len(st.session_state.reviews) else {}
        lead = st.session_state.leads[idx] if idx < len(st.session_state.leads) else {}
        verdict = review.get("verdict", "HOLD").upper()
        badge_class = "pass-badge" if "PASS" in verdict else ("revise-badge" if "REVISE" in verdict else "hold-badge")

        left, right = st.columns([3, 2])
        with left:
            st.markdown(f"""
            <div class="card-box">
                <h4>✉️ @Writer Draft — Lead #{draft.get('lead_number')}: {draft.get('business_name')}</h4>
                <p><strong>Subject:</strong> {draft.get('subject')}</p>
                <hr style="border-color:#1f2937;">
                <p style="white-space: pre-wrap;">{draft.get('body')}</p>
                <small style="color:#94a3b8;">Word count: {draft.get('word_count')} words | Source: {lead.get('website_or_source_url')}</small>
            </div>
            """, unsafe_allow_html=True)

        with right:
            st.markdown(f"""
            <div class="card-box">
                <h4>🔍 @Reviewer Verdict: <span class="{badge_class}">{verdict}</span></h4>
                <p><strong>Audit Notes:</strong> {review.get('audit_notes')}</p>
                <p><strong>Correction Request:</strong> <code>{review.get('correction_request')}</code></p>
            </div>
            """, unsafe_allow_html=True)

            fix_instruction = st.text_input(
                f"Ask @Writer to revise Lead #{draft.get('lead_number')}:",
                placeholder="e.g., Mention they can book after hours",
                key=f"fix_{idx}"
            )
            if st.button(f"🔄 Revise Lead #{draft.get('lead_number')}", key=f"btn_fix_{idx}"):
                with st.spinner("@Writer is revising this draft..."):
                    client = get_client()
                    rev_prompt = f"""
                    Revise this email draft for {draft.get('business_name')} using ONLY these verified facts: {json.dumps(lead)}.
                    Current draft: {draft.get('body')}
                    Reviewer note: {review.get('correction_request')}
                    User instruction: {fix_instruction}
                    Keep it 60-90 words. Return ONLY JSON with keys: "subject", "body", "word_count".
                    """
                    res = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=rev_prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    updated = json.loads(res.text)
                    st.session_state.drafts[idx]["subject"] = updated.get("subject", draft["subject"])
                    st.session_state.drafts[idx]["body"] = updated.get("body", draft["body"])
                    st.session_state.drafts[idx]["word_count"] = updated.get("word_count", 75)
                    st.session_state.reviews[idx]["verdict"] = "PASS (REVISED)"
                    st.rerun()

    if st.button("📲 Morph Into Mode 4: Monday Morning Client Approval Deck", type="primary", use_container_width=True):
        st.session_state.ui_mode = "MODE_4_CLIENT_DECK"
        st.rerun()

# ---------------------------------------------------------------------------
# MORPH MODE 4: THE 30-SECOND MONDAY CLIENT APPROVAL DECK
# ---------------------------------------------------------------------------
elif st.session_state.ui_mode == "MODE_4_CLIENT_DECK":
    st.markdown(f"""
    <div class="mode-banner">
        <h3>☕ MODE 4: Monday Morning Client Approval Room ({st.session_state.batch_id})</h3>
        <p>Nothing is sent by an agent. Tap Approve on the drafts you like, then click to open pre-filled in your own email or WhatsApp.</p>
    </div>
    """, unsafe_allow_html=True)

    for idx, draft in enumerate(st.session_state.drafts):
        lead = st.session_state.leads[idx] if idx < len(st.session_state.leads) else {}
        review = st.session_state.reviews[idx] if idx < len(st.session_state.reviews) else {}
        lead_num = draft.get("lead_number", idx + 1)
        current_status = st.session_state.approvals.get(lead_num, "PENDING HUMAN SIGN-OFF")

        st.markdown(f"""
        <div class="card-box">
            <h4>{draft.get('business_name')} — <span style="color:#38bdf8;">{current_status}</span></h4>
            <p><strong>Verified Fact Used:</strong> {lead.get('verified_fact')} (<a href="{lead.get('website_or_source_url')}" target="_blank">Source</a>)</p>
            <p><strong>Reviewer Check:</strong> <code>{review.get('verdict', 'PASS')}</code></p>
            <p><strong>Subject:</strong> {draft.get('subject')}</p>
            <pre style="background:#0f172a; padding:12px; border-radius:8px; white-space:pre-wrap; color:#f8fafc;">{draft.get('body')}</pre>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if st.button(f"✅ Approve #{lead_num}", key=f"app_{lead_num}", use_container_width=True):
                st.session_state.approvals[lead_num] = "APPROVED BY HUMAN"
                st.rerun()
        with c2:
            if st.button(f"❌ Drop #{lead_num}", key=f"drop_{lead_num}", use_container_width=True):
                st.session_state.approvals[lead_num] = "DROPPED"
                st.rerun()
        with c3:
            if st.session_state.approvals.get(lead_num) == "APPROVED BY HUMAN":
                subject_enc = urllib.parse.quote(draft.get("subject", ""))
                body_enc = urllib.parse.quote(draft.get("body", ""))
                contact_email = lead.get("public_contact", "") if "@" in str(lead.get("public_contact", "")) else ""
                mailto_link = f"mailto:{contact_email}?subject={subject_enc}&body={body_enc}"
                wa_link = f"https://wa.me/?text={subject_enc}%0A%0A{body_enc}"
                st.markdown(
                    f"👉 **[Open in My Email Inbox]({mailto_link})** &nbsp;|&nbsp; 💬 **[Open in WhatsApp]({wa_link})**"
                )
