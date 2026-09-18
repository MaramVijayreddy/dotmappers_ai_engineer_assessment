import os, requests
import streamlit as st

st.set_page_config(page_title="AI Support Ticket Analytics", page_icon="📊", layout="wide")
st.title("AI Support Ticket Analytics")
st.caption("Natural-language analytics + anomaly detection")
base = st.sidebar.text_input("API URL", os.getenv("API_URL", "http://localhost:8000"))

st.subheader("Ask the ticket data")
q = st.text_input("Question", placeholder="How many critical tickets are unresolved?")
if st.button("Ask", type="primary") and q:
    try:
        r = requests.post(f"{base}/query", json={"question":q}, timeout=180)
        if r.ok:
            x=r.json(); st.success(x["answer"]); st.json(x["intent"]); st.dataframe(x["data"], use_container_width=True)
        else: st.error(r.text)
    except Exception as e: st.error(str(e))

st.divider(); st.subheader("Anomaly detection")
if st.button("Detect anomalies"):
    try:
        r = requests.post(
            f"{base}/anomalies",
            json={
                "resolution_iqr_multiplier": 1.5,
                "unresolved_age_hours": 24,
                "time_range": {
                    "kind": "this_week",
                    "start": None,
                    "end": None
                }
            },
            timeout=60
            )
        if r.ok:
            x=r.json(); st.metric("Anomalies", x["anomaly_count"]); st.caption(f"Dataset anchor: {x['anchor_timestamp']}"); st.dataframe(x["anomalies"], use_container_width=True)
        else: st.error(r.text)
    except Exception as e: st.error(str(e))

st.divider();
st.caption("Assessment-aligned interface. API is the source of truth; the UI does not compute answers itself.")
