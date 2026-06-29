import streamlit as st
import pandas as pd
import numpy as np
import io
from modules.forecast import run_forecast, SUBSEGMENTS_HAN, SUBSEGMENTS_SGN
from modules.data_loader import (
    load_history, filter_history, exclude_tet,
    build_day_variables, build_week_variables
)

st.set_page_config(
    page_title="Driver Supply Forecast",
    page_icon="🚚",
    layout="wide"
)

st.title("🚚 Driver Supply Forecast — Ahamove")
st.caption("Automation Forecast Driver v0.3")

# ─── Sidebar config ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Cấu hình")
    region = st.selectbox("Region", ["HAN", "SGN"])
    granularity = st.selectbox("Granularity", ["day", "week", "month"])
    fc_types = st.multiselect(
        "FC types cần chạy",
        ["all", "excbulky", "4h", "gxt"],
        default=["all", "excbulky"]
    )
    st.divider()
    st.caption(f"Subsegments: {', '.join(SUBSEGMENTS_HAN if region == 'HAN' else SUBSEGMENTS_SGN)}")

# ─── Step 1: Upload FC Raw ────────────────────────────────────────────────────
st.header("① Upload FC Raw")
st.caption("File Excel/CSV với cột: date | all_service | bulky | gxt | excbulky")

uploaded = st.file_uploader(
    f"Upload FC Raw — {region}",
    type=["csv", "xlsx"],
    key="fc_raw"
)

fc_raw_df = None
if uploaded:
    try:
        if uploaded.name.endswith(".xlsx"):
            fc_raw_df = pd.read_excel(uploaded)
        else:
            fc_raw_df = pd.read_csv(uploaded)

        fc_raw_df.columns = fc_raw_df.columns.str.strip().str.lower()
        fc_raw_df["date"] = pd.to_datetime(fc_raw_df["date"])
        fc_raw_df = fc_raw_df.sort_values("date").reset_index(drop=True)

        st.success(f"✅ Đã đọc {len(fc_raw_df)} ngày — {fc_raw_df['date'].min().date()} → {fc_raw_df['date'].max().date()}")
        with st.expander("Xem FC Raw"):
            st.dataframe(fc_raw_df, use_container_width=True)
    except Exception as e:
        st.error(f"Lỗi đọc file: {e}")

# ─── Step 2: Load History ─────────────────────────────────────────────────────
st.header("② Load History")

if st.button("🔄 Load history từ Google Sheets", disabled=fc_raw_df is None):
    with st.spinner("Đang đọc history..."):
        try:
            hist = load_history(granularity)
            st.session_state["hist_raw"] = hist
            st.success(f"✅ History {granularity}: {len(hist):,} dòng")
        except Exception as e:
            st.error(f"Lỗi load history: {e}")

if "hist_raw" in st.session_state:
    st.caption(f"History loaded: {len(st.session_state['hist_raw']):,} dòng")

# ─── Step 3: Generate Preview ─────────────────────────────────────────────────
st.header("③ Generate Preview")

can_run = (
    fc_raw_df is not None and
    "hist_raw" in st.session_state and
    len(fc_types) > 0
)

if st.button("🚀 Generate Preview", disabled=not can_run, type="primary"):
    hist_raw = st.session_state["hist_raw"]
    results = {}

    with st.spinner("Đang tính toán..."):
        dates = fc_raw_df["date"].tolist()

        # Build X variables cho kỳ dự báo
        if granularity == "day":
            X_future = build_day_variables(dates)
        elif granularity == "week":
            week_starts = fc_raw_df.groupby(
                fc_raw_df["date"].dt.to_period("W")
            )["date"].min().tolist()
            X_future = build_week_variables(week_starts)
        else:
            X_future = None  # month dùng FORECAST riêng

        X_hist = None  # sẽ build riêng cho từng fc_type bên dưới

        for fc_type in fc_types:
            try:
                # Volume series từ FC Raw
                col_map = {
                    "all":      "all_service",
                    "excbulky": "excbulky",
                    "4h":       "bulky",
                    "gxt":      "gxt"
                }
                vol_col = col_map.get(fc_type, "all_service")
                if vol_col not in fc_raw_df.columns:
                    st.warning(f"Không tìm thấy cột '{vol_col}' trong FC Raw — bỏ qua {fc_type}")
                    continue

                fc_raw_volume = fc_raw_df.set_index("date")[vol_col]

                # Filter history
                hist_filtered = filter_history(hist_raw, fc_type, region)

                # Build X_hist từ periods của hist_filtered (không phải toàn bộ hist_raw)
                if granularity == "day":
                    filtered_dates = exclude_tet(
                        hist_filtered[["period"]].drop_duplicates(), "period"
                    )["period"].tolist()
                    X_hist = build_day_variables(filtered_dates)
                elif granularity == "week":
                    filtered_dates = exclude_tet(
                        hist_filtered[["period"]].drop_duplicates(), "period"
                    )["period"].tolist()
                    X_hist = build_week_variables(filtered_dates)
                else:
                    X_hist = None

                # Run
                res = run_forecast(
                    fc_raw_volume=fc_raw_volume,
                    hist_df=hist_filtered,
                    X_future=X_future,
                    X_hist=X_hist,
                    fc_type=fc_type,
                    region=region
                )
                results[fc_type] = res

            except Exception as e:
                st.error(f"Lỗi FC {fc_type}: {e}")

    st.session_state["results"] = results
    st.session_state["fc_raw_df"] = fc_raw_df
    st.session_state["region"] = region
    st.session_state["granularity"] = granularity
    st.success("✅ Forecast xong!")

# ─── Preview results ──────────────────────────────────────────────────────────
if "results" in st.session_state and st.session_state["results"]:
    st.divider()
    st.header("④ Preview kết quả")
    results = st.session_state["results"]

    for fc_type, res in results.items():
        with st.expander(f"📊 FC {fc_type.upper()} — {st.session_state['region']}", expanded=True):
            tab1, tab2, tab3, tab4 = st.tabs(["% Comp", "Comp", "Prod", "Active"])

            with tab1:
                st.dataframe(res["pct_comp"].style.format("{:.1%}"), use_container_width=True)
            with tab2:
                st.dataframe(res["comp"].style.format("{:.0f}"), use_container_width=True)
                # Constraint check
                check = res["check"]
                raw_vol = st.session_state["fc_raw_df"].set_index("date")[
                    {"all": "all_service", "excbulky": "excbulky", "4h": "bulky", "gxt": "gxt"}[fc_type]
                ]
                diff = (check - raw_vol).abs().max()
                if diff < 0.01:
                    st.success("✅ Constraint OK — Σ Comp = FC Raw (không lệch)")
                else:
                    st.error(f"⚠️ Lệch tối đa: {diff:.2f} — cần kiểm tra lại")
            with tab3:
                st.dataframe(res["prod"].style.format("{:.2f}"), use_container_width=True)
            with tab4:
                st.dataframe(res["active"].style.format("{:.0f}"), use_container_width=True)

    # ─── Step 4: Confirm & Export ─────────────────────────────────────────────
    st.divider()
    st.header("⑤ Confirm & Export")
    st.caption("Review xong bấm để xuất Excel hoặc push lên Google Sheets")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📥 Download Excel", type="primary"):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                for fc_type, res in results.items():
                    prefix = f"{st.session_state['region']}_{fc_type}"
                    res["pct_comp"].to_excel(writer, sheet_name=f"{prefix}_pct_comp")
                    res["comp"].to_excel(writer, sheet_name=f"{prefix}_comp")
                    res["prod"].to_excel(writer, sheet_name=f"{prefix}_prod")
                    res["active"].to_excel(writer, sheet_name=f"{prefix}_active")
            output.seek(0)
            st.download_button(
                label="⬇️ Tải file Excel",
                data=output,
                file_name=f"FC_Driver_{st.session_state['region']}_{st.session_state['granularity']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    with col2:
        st.button("☁️ Push lên Google Sheets (coming soon)", disabled=True)
