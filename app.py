import streamlit as st
import pytesseract
from PIL import Image
import fitz  # PyMuPDF
import docx2txt
import os
import re
from langchain.chat_models import ChatOpenAI

# ---------- UTILITIES ----------

def extract_text_from_file(uploaded_file):
    ext = uploaded_file.name.lower()
    if ext.endswith(".pdf"):
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        return "\n".join([page.get_text() for page in doc])
    elif ext.endswith(".docx"):
        return docx2txt.process(uploaded_file)
    elif ext.endswith((".jpg", ".jpeg", ".png")):
        image = Image.open(uploaded_file)
        return pytesseract.image_to_string(image)
    else:
        return "Unsupported file type."

def extract_deal_metrics(text):
    metrics = {}
    price_match = re.search(r'\$\s?[\d,]+(?:\.\d{2})?', text)
    if price_match:
        price = float(price_match.group().replace("$", "").replace(",", ""))
        metrics['Asking Price'] = f"${price:,.2f}"
    else:
        price = None

    units_match = re.search(r'(\d{1,3})\s+(unit|units)', text, re.IGNORECASE)
    if units_match:
        metrics['Units'] = units_match.group(1)

    noi_match = re.search(r'NOI\s*[:=]?\s*\$?([\d,]+(?:\.\d{2})?)', text, re.IGNORECASE)
    if noi_match:
        noi = float(noi_match.group(1).replace(",", ""))
        metrics['NOI'] = f"${noi:,.2f}"
    else:
        noi = None

    cap_rate_match = re.search(r'Cap\s*Rate\s*[:=]?\s*(\d{1,2}\.\d{1,2})%', text, re.IGNORECASE)
    if cap_rate_match:
        cap_rate = float(cap_rate_match.group(1))
        metrics['Cap Rate'] = f"{cap_rate:.2f}%"
    else:
        cap_rate = None

    if noi and price and not cap_rate_match:
        est_cap_rate = (noi / price) * 100
        metrics['Estimated Cap Rate'] = f"{est_cap_rate:.2f}%"
    if cap_rate and price and not noi_match:
        est_noi = (cap_rate / 100) * price
        metrics['Estimated NOI'] = f"${est_noi:,.2f}"

    if noi:
        est_gross = noi / 0.65
        est_opex = est_gross * 0.35
        metrics['Estimated OpEx'] = f"${est_opex:,.2f}"

    if 'Units' in metrics:
        est_capex = int(metrics['Units']) * 8000
        metrics['Estimated CapEx'] = f"${est_capex:,.2f}"

    rent_roll_match = re.findall(r'(\d{1,3})\s+sqft\s+@\s+\$?(\d+(\.\d{1,2})?)', text, re.IGNORECASE)
    if rent_roll_match:
        metrics['Detected Rent Roll Entries'] = len(rent_roll_match)
        total_monthly = sum(int(sqft) * float(rate) for sqft, rate, _ in rent_roll_match)
        metrics['Estimated Gross Monthly Rent'] = f"${total_monthly:,.2f}"
        metrics['Estimated Annual Rent'] = f"${(total_monthly * 12):,.2f}"

    return metrics

def build_analysis_prompt(user_goal, extracted_text):
    return f"""
Act as a commercial real estate analyst. I have uploaded the following deal document or information:

{extracted_text[:1500]}...

The user asked: "{user_goal}"

Based on the document and request, provide:
- A deal summary
- Key financial terms (price, cap rate, NOI, value-add potential)
- Red flags or things to consider
- Suggestions for improvement or negotiation
- Calculate renovation ROI assuming $8,000 per unit in CapEx and rent bump of $150/unit
"""

# ---------- STREAMLIT UI ----------

st.title("🏢 Real Estate Deal Analyzer Agent")

uploaded_file = st.file_uploader("Upload Deal Document (PDF, Image, DOCX)", type=["pdf", "jpg", "jpeg", "png", "docx"])
user_goal = st.text_input("Describe what you'd like to analyze (e.g. underwrite a deal, find red flags)")

if uploaded_file and user_goal:
    with st.spinner("Processing file and generating insights..."):
        extracted_text = extract_text_from_file(uploaded_file)
        extracted_metrics = extract_deal_metrics(extracted_text)
        prompt = build_analysis_prompt(user_goal, extracted_text)

        llm = ChatOpenAI(model_name="gpt-4", temperature=0)
        response = llm.predict(prompt)

        st.subheader("📄 Extracted Preview")
        st.text_area("Text from Document", extracted_text[:1500], height=200)

        st.subheader("📊 Detected Deal Metrics")
        for key, value in extracted_metrics.items():
            st.markdown(f"**{key}:** {value}")

        st.subheader("💡 Deal Analysis")
        st.write(response)

        st.download_button("Download Analysis", response, file_name="deal_analysis.txt")