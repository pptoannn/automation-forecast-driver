import streamlit as st

st.set_page_config(
    page_title="Automation Forecast Driver",
    page_icon="🚚",
    layout="wide"
)

st.title("🚚 Automation Forecast Driver")
st.caption("Ahamove — Driver Supply Forecasting")

st.info("🚧 Project đang được build. Upload Sheet A để bắt đầu.")

# Placeholder sections
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Trạng thái", "Đang setup", "")
with col2:
    st.metric("Phiên bản", "v0.1", "")
with col3:
    st.metric("Model", "Claude Sonnet", "")

st.divider()
st.subheader("📥 Input")
uploaded = st.file_uploader("Upload Sheet A (CSV hoặc Excel)", type=["csv", "xlsx"])
if uploaded:
    st.success(f"Đã nhận file: {uploaded.name}")
    st.info("Logic xử lý đang được build — coming soon.")
