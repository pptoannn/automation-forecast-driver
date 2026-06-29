import pandas as pd
import numpy as np
from datetime import date, timedelta
import requests
import os

SPREADSHEET_ID = "1ceGtSwznjgNLCcAoY0kRNve01ySSHOmN1DNmZuFud8o"

# Sheet GIDs
GID_FC_RAW_HAN      = "66932870"
GID_HISTORY_DAY     = "441226900"
GID_HISTORY_WEEK    = "2124194227"
GID_HISTORY_MONTH   = "477959512"

TET_MONTHS = [(2025, 1), (2025, 2), (2026, 1), (2026, 2)]

FC_TYPE_FILTERS = {
    "all":      {"Category": "ALL",   "SubCat": "ALL"},
    "excbulky": {"Category": "ALL",   "SubCat": "NOT_WH"},
    "4h":       {"Category": "BULKY", "SubCat": "NOT_WH"},
    "gxt":      {"Category": "GXT",   "SubCat": "NOT_WH"},
}


def _csv_url(gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"


def load_sheet(gid: str) -> pd.DataFrame:
    """Đọc sheet từ Google Sheets public link"""
    url = _csv_url(gid)
    session = requests.Session()
    resp = session.get(url, allow_redirects=True)
    resp.raise_for_status()
    from io import StringIO
    return pd.read_csv(StringIO(resp.text))


def load_history(granularity: str = "day") -> pd.DataFrame:
    """
    granularity: 'day' | 'week' | 'month'
    Trả về DataFrame đã parse period thành datetime
    """
    gid_map = {
        "day":   GID_HISTORY_DAY,
        "week":  GID_HISTORY_WEEK,
        "month": GID_HISTORY_MONTH,
    }
    df = load_sheet(gid_map[granularity])
    df.columns = df.columns.str.strip()
    df["period"] = pd.to_datetime(df["period"], dayfirst=False, errors="coerce")
    df = df.dropna(subset=["period"])

    # Chuẩn hóa tên cột
    df["FINAL_SEGMENT"] = df["FINAL_SEGMENT"].str.strip()
    df["Category"]      = df["Category"].str.strip().str.upper()
    df["SubCat"]        = df["SubCat"].str.strip().str.upper()  # chuẩn hóa uppercase

    numeric_cols = ["active", "total_rq", "total_comp", "AVG_prod"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def filter_history(df: pd.DataFrame, fc_type: str, region: str) -> pd.DataFrame:
    """
    Filter history theo fc_type và region.
    excbulky = ALL category nhưng loại GXT và BULKY ra khỏi SubCat
    """
    f = FC_TYPE_FILTERS[fc_type]

    if fc_type == "excbulky":
        # SubCat NOT_WH nhưng category là INSTANT + ECO + HM
        mask = (
            df["Category"].isin(["INSTANT", "ECO", "HM"]) &
            (df["SubCat"] == "NOT_WH")
        )
    else:
        mask = (
            (df["Category"] == f["Category"]) &
            (df["SubCat"] == f["SubCat"])
        )

    # Filter region qua FINAL_SEGMENT
    from modules.forecast import SUBSEGMENTS_HAN, SUBSEGMENTS_SGN
    segs = SUBSEGMENTS_HAN if region == "HAN" else SUBSEGMENTS_SGN
    mask &= df["FINAL_SEGMENT"].isin(segs)

    return df[mask].copy()


def exclude_tet(df: pd.DataFrame, period_col: str = "period") -> pd.DataFrame:
    mask = df[period_col].apply(lambda x: (x.year, x.month) not in TET_MONTHS)
    return df[mask].copy()


def parse_fc_raw(uploaded_file) -> pd.DataFrame:
    """
    Đọc file FC Raw do user upload (CSV hoặc Excel).
    Trả về DataFrame với các cột:
      date | all_service | bulky | gxt | excbulky
    """
    if hasattr(uploaded_file, "name") and uploaded_file.name.endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        df = pd.read_csv(uploaded_file)

    df.columns = df.columns.str.strip().str.lower()
    return df


def extract_fc_raw_volumes(df_raw: pd.DataFrame) -> dict:
    """
    Trích 4 series volume từ FC Raw.
    Trả về dict: {fc_type: pd.Series(index=date, values=comp)}

    Mong đợi df_raw có các cột: date, và các dòng với cột service/volume.
    Cấu trúc: mỗi dòng là 1 dịch vụ, mỗi cột là 1 ngày.
    """
    # Placeholder — sẽ được hoàn thiện sau khi xem cấu trúc FC Raw thực tế
    # User sẽ cần confirm tên cột chính xác
    raise NotImplementedError(
        "Cần xác nhận cấu trúc cột FC Raw với user trước khi implement"
    )


# ─── X variable builder ───────────────────────────────────────────────────────

DOUBLE_DATES = [
    (1, 1), (2, 2), (3, 3), (4, 4), (5, 5),
    (6, 6), (7, 7), (8, 8), (9, 9), (10, 10),
    (11, 11), (12, 12)
]
CAMPAIGN_WINDOW = 3  # số ngày campaign tính từ ngày trùng
DAY15_CAMPAIGN  = [15, 16]
MONTH_END_PEAK  = 25  # ngày 25 trở đi là peak cuối tháng


def build_day_variables(dates: list) -> pd.DataFrame:
    """
    Xây dựng X matrix cho từng ngày dự báo.
    dates: list of date objects
    Trả về DataFrame: index=dates, columns=[DayNo_dummy_var, Event, WeekVar]
    """
    rows = []
    for d in dates:
        dt = pd.Timestamp(d)

        dayno_dummy = 1 if dt.day >= MONTH_END_PEAK else 0
        weekvar     = 1 if dt.weekday() >= 5 else 0  # 5=Sat, 6=Sun

        # Event: ngày trùng (3 ngày liên tiếp) hoặc ngày 15-16
        event = 0
        for (m, day) in DOUBLE_DATES:
            if dt.month == m:
                event_start = pd.Timestamp(dt.year, m, day)
                for offset in range(CAMPAIGN_WINDOW):
                    if dt == event_start + pd.Timedelta(days=offset):
                        event = 1
        if dt.day in DAY15_CAMPAIGN:
            event = 1

        rows.append({
            "date":             dt,
            "DayNo_dummy_var":  dayno_dummy,
            "Event":            event,
            "WeekVar":          weekvar,
        })

    return pd.DataFrame(rows).set_index("date")


def build_week_variables(week_starts: list) -> pd.DataFrame:
    """
    X matrix cho FC week.
    week_starts: list of date (thứ 2 đầu tuần)
    Trả về DataFrame: index=week_starts, columns=[week_of_month, campaign_days]
    """
    rows = []
    for ws in week_starts:
        dt = pd.Timestamp(ws)
        week_of_month = (dt.day - 1) // 7 + 1

        # Đếm ngày campaign trong tuần (7 ngày từ ws)
        campaign_days = 0
        for offset in range(7):
            d = dt + pd.Timedelta(days=offset)
            for (m, day) in DOUBLE_DATES:
                if d.month == m:
                    event_start = pd.Timestamp(d.year, m, day)
                    for i in range(CAMPAIGN_WINDOW):
                        if d == event_start + pd.Timedelta(days=i):
                            campaign_days += 1
            if d.day in DAY15_CAMPAIGN:
                campaign_days += 1

        rows.append({
            "week_start":    dt,
            "week_of_month": week_of_month,
            "campaign_days": campaign_days,
        })

    return pd.DataFrame(rows).set_index("week_start")
