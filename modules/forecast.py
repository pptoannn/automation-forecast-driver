import pandas as pd
import numpy as np
from datetime import date

# ─── Constants ────────────────────────────────────────────────────────────────

TET_MONTHS = [(2025, 1), (2025, 2), (2026, 1), (2026, 2)]  # Tháng Tết bị loại

SUBSEGMENTS_HAN = [
    "CORE_HAN", "DN", "Growth", "High", "HTX",
    "Low", "Medium", "METATRUCK", "Return", "TAI_HAN"
]
SUBSEGMENTS_SGN = [
    "METATRUCK", "DN", "HTX", "CORE_SGN", "CORE_BDG",
    "CORE_DNI", "TAI_SGN", "TRICYCLE", "High", "Medium",
    "Low", "Growth", "Return"
]

# Tệp chỉ có volume trong GXT (còn lại = 0)
GXT_SEGMENTS = {"METATRUCK", "DN"}

# Tệp residual
HAN_RESIDUAL = "METATRUCK"
SGN_RESIDUAL_POOL = ["High", "Medium", "Low", "Return", "Growth"]  # chia theo tỷ trọng 3 kỳ gần nhất

# Rule method cứng (override CV)
FORCE_MULTIREG_COMP = {
    "all":      ["CORE_HAN", "METATRUCK", "TAI_HAN", "CORE_SGN", "TAI_SGN"],
    "excbulky": ["CORE_HAN", "METATRUCK", "TAI_HAN", "CORE_SGN", "TAI_SGN"],
    "4h":       ["METATRUCK"],
    "gxt":      ["METATRUCK"],
}
FORCE_MA_COMP = ["High"]  # luôn dùng MA k=3 cho %comp, bất kể CV
FORCE_MULTIREG_PROD = "all"  # tất cả tệp dùng MultiReg cho prod, trừ High
FORCE_MA_PROD = ["High"]     # High dùng MA/Flat Mean nếu biến động mạnh

CV_FLAT_MEAN   = 0.15
CV_MULTIREG    = 0.30  # 15%-30% → MultiReg, ≥30% → MA


# ─── Utils ───────────────────────────────────────────────────────────────────

def is_tet(period: pd.Timestamp) -> bool:
    return (period.year, period.month) in TET_MONTHS


def exclude_tet(df: pd.DataFrame, period_col: str = "period") -> pd.DataFrame:
    mask = df[period_col].apply(lambda x: not is_tet(pd.Timestamp(x)))
    return df[mask].copy()


def calc_cv(series: pd.Series) -> float:
    mean = series.mean()
    if mean == 0:
        return 0.0
    return series.std() / mean


def select_method(cv: float, segment: str, fc_type: str, metric: str) -> str:
    """
    Trả về: 'flat_mean' | 'multireg' | 'ma'
    metric: 'comp' (cho %comp) hoặc 'prod'
    """
    if metric == "comp":
        if segment in FORCE_MA_COMP:
            return "ma"
        forced = FORCE_MULTIREG_COMP.get(fc_type, [])
        if segment in forced:
            return "multireg"
    elif metric == "prod":
        if segment in FORCE_MA_PROD:
            return "ma"
        return "multireg"  # mặc định prod luôn multireg

    # CV-based selection
    if cv < CV_FLAT_MEAN:
        return "flat_mean"
    elif cv < CV_MULTIREG:
        return "multireg"
    else:
        return "ma"


# ─── Forecasting methods ─────────────────────────────────────────────────────

def flat_mean(series: pd.Series) -> float:
    return series.mean()


def moving_average(series: pd.Series, k: int = 3) -> float:
    """MA k kỳ gần nhất (đã loại Tết trước khi truyền vào)"""
    return series.tail(k).mean()


def multireg_forecast(
    y: pd.Series,
    X_hist: pd.DataFrame,
    X_future: pd.DataFrame
) -> pd.Series:
    """
    OLS regression (LINEST equivalent):
    Y = β_WeekVar*WeekVar + β_Event*Event + β_DayNo*DayNo_dummy_var + intercept

    Tự align X_hist với y theo index (date) để tránh dimension mismatch.
    """
    # Align X_hist với y theo index
    common_idx = y.index.intersection(X_hist.index)
    if len(common_idx) < 4:
        # Không đủ data → fallback flat mean
        val = float(y.mean()) if len(y) > 0 else 0.0
        return pd.Series(val, index=X_future.index)

    y_aligned = y.loc[common_idx]
    X_aligned = X_hist.loc[common_idx, ["DayNo_dummy_var", "Event", "WeekVar"]].values

    ones = np.ones((X_aligned.shape[0], 1))
    X_with_const = np.hstack([X_aligned, ones])

    coeffs, _, _, _ = np.linalg.lstsq(X_with_const, y_aligned.values, rcond=None)
    beta_dayno, beta_event, beta_weekvar, intercept = coeffs

    X_pred = X_future[["DayNo_dummy_var", "Event", "WeekVar"]].values
    predictions = (
        beta_dayno   * X_pred[:, 0] +
        beta_event   * X_pred[:, 1] +
        beta_weekvar * X_pred[:, 2] +
        intercept
    )
    return pd.Series(np.maximum(0, predictions), index=X_future.index)


# ─── %comp calculation ────────────────────────────────────────────────────────

def calc_pct_comp_history(hist: pd.DataFrame, segments: list) -> pd.DataFrame:
    """
    Từ raw history, tính %comp của từng segment theo từng kỳ.
    hist phải có cột: period, FINAL_SEGMENT, total_comp
    """
    pivot = hist.pivot_table(
        index="period", columns="FINAL_SEGMENT",
        values="total_comp", aggfunc="sum", fill_value=0
    )
    total = pivot.sum(axis=1)
    pct = pivot.div(total, axis=0).fillna(0)
    # Chỉ giữ segments cần thiết
    for seg in segments:
        if seg not in pct.columns:
            pct[seg] = 0.0
    return pct[segments]


def forecast_pct_comp(
    pct_hist: pd.DataFrame,
    X_hist: pd.DataFrame,
    X_future: pd.DataFrame,
    fc_type: str,
    region: str
) -> pd.DataFrame:
    """
    Dự báo %comp cho từng segment.
    Trả về DataFrame: index = X_future.index, columns = segments
    """
    segments = pct_hist.columns.tolist()
    result = pd.DataFrame(index=X_future.index, columns=segments, dtype=float)

    for seg in segments:
        series = exclude_tet(
            pct_hist[[seg]].reset_index().rename(columns={"period": "period"}),
            "period"
        )[seg]

        # GXT: chỉ METATRUCK và DN có volume
        if fc_type == "gxt" and seg not in GXT_SEGMENTS:
            result[seg] = 0.0
            continue

        cv = calc_cv(series)
        method = select_method(cv, seg, fc_type, "comp")

        if method == "flat_mean":
            val = flat_mean(series)
            result[seg] = val
        elif method == "ma":
            val = moving_average(series, k=3)
            result[seg] = val
        elif method == "multireg":
            result[seg] = multireg_forecast(series, X_hist, X_future)

    return result.astype(float)


# ─── Prod calculation ─────────────────────────────────────────────────────────

def forecast_prod(
    prod_hist: pd.DataFrame,
    X_hist: pd.DataFrame,
    X_future: pd.DataFrame,
    fc_type: str
) -> pd.DataFrame:
    """
    Dự báo prod cho từng segment.
    prod_hist: index = period, columns = segments, values = AVG_prod
    """
    segments = prod_hist.columns.tolist()
    result = pd.DataFrame(index=X_future.index, columns=segments, dtype=float)

    for seg in segments:
        series = exclude_tet(
            prod_hist[[seg]].reset_index().rename(columns={"period": "period"}),
            "period"
        )[seg]

        cv = calc_cv(series)
        method = select_method(cv, seg, fc_type, "prod")

        if method == "flat_mean":
            result[seg] = flat_mean(series)
        elif method == "ma":
            result[seg] = moving_average(series, k=3)
        elif method == "multireg":
            result[seg] = multireg_forecast(series, X_hist, X_future)

    return result.astype(float)


# ─── Residual normalization ───────────────────────────────────────────────────

def normalize_pct_comp(
    pct_df: pd.DataFrame,
    region: str,
    pct_hist: pd.DataFrame
) -> pd.DataFrame:
    """
    Đảm bảo tổng %comp = 100% bằng cách điều chỉnh residual.

    HAN: METATRUCK = 1 - Σ các tệp khác
    SGN: residual chia theo tỷ trọng 3 kỳ gần nhất (loại Tết) cho 5 tệp
    """
    df = pct_df.copy()

    if region == "HAN":
        non_residual = [c for c in df.columns if c != HAN_RESIDUAL]
        df[HAN_RESIDUAL] = (1 - df[non_residual].sum(axis=1)).clip(lower=0)

    elif region == "SGN":
        non_pool = [c for c in df.columns if c not in SGN_RESIDUAL_POOL]
        residual = (1 - df[non_pool].sum(axis=1)).clip(lower=0)

        # Tỷ trọng lịch sử 3 kỳ gần nhất (loại Tết)
        hist_clean = exclude_tet(pct_hist.reset_index(), "period").set_index("period")
        pool_hist = hist_clean[SGN_RESIDUAL_POOL].tail(3).mean()
        pool_total = pool_hist.sum()
        if pool_total > 0:
            weights = pool_hist / pool_total
        else:
            weights = pd.Series(1 / len(SGN_RESIDUAL_POOL), index=SGN_RESIDUAL_POOL)

        for seg in SGN_RESIDUAL_POOL:
            df[seg] = df[seg] + residual * weights[seg]

    return df


def handle_htx_han(df_comp: pd.DataFrame) -> pd.DataFrame:
    """HTX HAN không còn hoạt động: chuyển volume sang METATRUCK"""
    if "HTX" in df_comp.columns and "METATRUCK" in df_comp.columns:
        df_comp["METATRUCK"] += df_comp["HTX"]
        df_comp["HTX"] = 0.0
    return df_comp


# ─── Main FC engine ───────────────────────────────────────────────────────────

def run_forecast(
    fc_raw_volume: pd.Series,  # index = date, values = total comp cần đạt
    hist_df: pd.DataFrame,     # raw history đã filter đúng Category + SubCat
    X_future: pd.DataFrame,    # các biến X cho kỳ dự báo (DayNo_dummy_var, Event, WeekVar)
    X_hist: pd.DataFrame,      # các biến X của kỳ lịch sử (cùng cấu trúc)
    fc_type: str,              # 'all' | 'excbulky' | '4h' | 'gxt'
    region: str                # 'HAN' | 'SGN'
) -> dict:
    """
    Trả về dict:
    {
        'pct_comp': DataFrame (index=date, columns=segments),
        'comp':     DataFrame (index=date, columns=segments),
        'prod':     DataFrame (index=date, columns=segments),
        'active':   DataFrame (index=date, columns=segments),
        'check':    Series (tổng comp theo ngày — phải = fc_raw_volume)
    }
    """
    segments = SUBSEGMENTS_HAN if region == "HAN" else SUBSEGMENTS_SGN

    # 1. Lịch sử %comp
    pct_hist = calc_pct_comp_history(hist_df, segments)

    # 2. Lịch sử prod
    prod_hist = hist_df.pivot_table(
        index="period", columns="FINAL_SEGMENT",
        values="AVG_prod", aggfunc="mean", fill_value=0
    ).reindex(columns=segments, fill_value=0)

    # 3. FC %comp
    pct_fc = forecast_pct_comp(pct_hist, X_hist, X_future, fc_type, region)

    # 4. Normalize residual
    pct_fc = normalize_pct_comp(pct_fc, region, pct_hist)

    # 5. FC Prod
    prod_fc = forecast_prod(prod_hist, X_hist, X_future, fc_type)

    # 6. FC Comp = FC Raw × %comp
    comp_fc = pct_fc.multiply(fc_raw_volume.values, axis=0)

    # 7. HTX HAN → METATRUCK
    if region == "HAN":
        comp_fc = handle_htx_han(comp_fc)

    # 8. FC Active = CEILING(Comp / Prod)
    active_fc = np.ceil(comp_fc.div(prod_fc.replace(0, np.nan))).fillna(0).astype(int)

    # 9. Constraint check
    check = comp_fc.sum(axis=1)

    return {
        "pct_comp": pct_fc,
        "comp":     comp_fc,
        "prod":     prod_fc,
        "active":   active_fc,
        "check":    check
    }
