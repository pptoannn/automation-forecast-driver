# Driver Supply Forecast — Business Logic

> Cập nhật: 2026-06-29 | Version: v0.2

---

## 1. Tổng quan luồng tính

```
FC Raw (demand từ sale theo ngày)
    ↓ Trích 4 series volume
    ↓
┌─────────────────────────────────────────┐
│  All Service | ExcBulky | 4H | GXT      │
└─────────────────────────────────────────┘
    ↓ Với mỗi series × từng subsegment
    ↓
FC %comp  (CV-based method)   FC Prod  (ưu tiên Mult.Reg)
    ↓                              ↓
FC Comp = FC Raw × FC %comp        │
    ↓                              │
FC Active = CEILING(FC Comp / FC Prod)

RÀNG BUỘC: Σ FC Comp tất cả subsegment = FC Raw (không được lệch)
```

---

## 2. Input data

### 2.1 FC Raw (demand từ sale)
Trích các dòng sau, bỏ qua các dòng khác:

| Dòng cần lấy | Dùng để làm FC |
|-------------|---------------|
| Total All Service | FC All |
| Total Bulky | FC 4H |
| Total GXT | FC GXT |
| Instant + Eco + HM (cộng lại) | FC ExcBulky |

- Theo **ngày**: dùng trực tiếp cho FC day
- Theo **tuần**: cộng các ngày trong tuần (T2 → CN)
- Theo **tháng**: cộng tất cả ngày trong tháng

### 2.2 Raw History
Các cột cần dùng:

| Cột | Ý nghĩa |
|-----|---------|
| `period` | Ngày (day), đầu tuần (week), đầu tháng (month) |
| `FINAL_SEGMENT` | Subsegment tài xế |
| `Category` | Dịch vụ (ALL, BULKY, GXT, INSTANT, ECO, HM...) |
| `SubCat` | `all` cho FC All; `NOT_WH` cho tất cả FC còn lại |
| `active` | Lịch sử active → pivot ra được |
| `total_comp` | Lịch sử comp → tính %comp |
| `AVG_prod` | Lịch sử prod → tính FC prod |

---

## 3. Subsegments

### HAN
`CORE_HAN | DN | Growth | High | HTX | Low | Medium | METATRUCK | Return | TAI_HAN`

### SGN
`METATRUCK | DN | HTX | CORE_SGN | CORE_BDG | CORE_DNI | TAI_SGN | TRICYCLE | High | Medium | Low | Growth | Return`

> HAN và SGN xử lý **độc lập**, input riêng, output riêng, không trộn lẫn.

---

## 4. Output types

| FC Type | Granularity | Output | SubCat filter |
|---------|------------|--------|---------------|
| All Service | Day / Week / Month | Internal | `all` |
| ExcBulky | Day | External (Exec view) | `NOT_WH` |
| 4H (Bulky) | Day | Internal | `NOT_WH` |
| GXT | Day | Internal | `NOT_WH` |

---

## 5. Phương pháp dự báo

### 5.1 CV thresholds
```
CV = σ / μ  (loại bỏ tháng Tết trước khi tính)

CV < 15%          → Flat Mean
15% ≤ CV < 30%    → Multiple Regression
CV ≥ 30%          → Moving Average (MA k=3)
```

### 5.2 Multiple Regression (LINEST)
```python
Y = lịch sử %comp hoặc prod (ghép 2 dãy để loại Tết)
X = [DayNo_dummy_var, Event, WeekVar]

FC = MAX(0,
    β_WeekVar    × WeekVar    +
    β_Event      × Event      +
    β_DayNo      × DayNo_dummy_var +
    intercept
)
```

**Biến X (Day level):**
| Biến | Định nghĩa |
|------|-----------|
| `DayNo_dummy_var` | 1 nếu ngày 25–hết tháng |
| `Event` | 1 nếu là ngày campaign: ngày trùng (1/1,2/2...) → 3 ngày liên tiếp; ngày 15 → ngày 15,16 |
| `WeekVar` | 1 nếu thứ 7 hoặc CN |

**Biến X (Week level):**
| Biến | Định nghĩa |
|------|-----------|
| `week_of_month` | Tuần thứ mấy trong tháng |
| `campaign_days` | Tổng số ngày campaign trong tuần |

### 5.3 Moving Average
- Window: k=3 kỳ gần nhất (tháng/tuần/ngày tùy granularity)
- Loại bỏ kỳ Tết trước khi tính
- EMA k=3 có thể dùng nếu MA cho kết quả kém

### 5.4 Flat Mean
- Trung bình đơn giản của toàn bộ lịch sử (loại bỏ Tết)

---

## 6. Rule theo từng FC type

### FC Day — All Service
| Subsegment | %comp method | Prod method |
|------------|-------------|-------------|
| CORE_HAN, METATRUCK, TAI_HAN, CORE_SGN, TAI_SGN | Multiple Regression | Multiple Regression |
| High | Moving Average k=3 | Flat Mean / MA nếu biến động mạnh |
| Còn lại | Theo CV | Multiple Regression |

### FC Day — ExcBulky (Exclude GXT/4H)
| Subsegment | %comp method | Prod method |
|------------|-------------|-------------|
| CORE_HAN, METATRUCK, TAI_HAN, CORE_SGN, TAI_SGN | Multiple Regression | Multiple Regression |
| High (HAN + SGN) | Moving Average k=3 | Flat Mean / MA |
| Còn lại | Theo CV | Multiple Regression |

### FC Day — 4H (Bulky)
| Subsegment | %comp method | Prod method |
|------------|-------------|-------------|
| METATRUCK | Multiple Regression | Multiple Regression |
| Còn lại | Theo CV | Multiple Regression |

### FC Day — GXT
| Subsegment | Volume |
|------------|--------|
| METATRUCK, DN | Có volume — tính FC bình thường |
| Tất cả tệp còn lại | = 0 (không phân bổ) |

%comp method:
- METATRUCK: Multiple Regression
- DN: Theo CV (Flat Mean hoặc MA)
- Prod: Multiple Regression cho tất cả

### FC Week — All Service
| Metric | Method |
|--------|--------|
| %comp | FORECAST (Google Sheets built-in) |
| Prod | Multiple Regression (week variables) |

### FC Month — All Service
| Metric | Method |
|--------|--------|
| %comp | FORECAST (Google Sheets built-in) |
| Prod | FORECAST (Google Sheets built-in) |

---

## 7. Special rules

### 7.1 Loại bỏ Tết
- Loại bỏ data các tháng Tết (thường tháng 1–2) khỏi lịch sử khi tính CV, Mean, MA, Regression
- Kỹ thuật: ghép 2 dãy array `{rows_trước_Tết ; rows_sau_Tết}` để LINEST/tính toán bỏ qua

### 7.2 HTX HAN
- HTX HAN không còn hoạt động → nếu FC ra > 0, chuyển toàn bộ sang METATRUCK
- Áp dụng cho cả comp và prod

### 7.3 Residual — đảm bảo Σ%comp = 100%

**HAN:**
- METATRUCK = 100% − Σ tất cả tệp khác

**SGN:**
- Residual phân bổ theo tỷ trọng lịch sử cho 5 tệp: High, Medium, Low, Return, Growth
- Công thức: residual_tệp = total_residual × (avg_hist_%comp_tệp / Σ avg_hist_%comp_5_tệp)
- avg_hist_%comp tính theo **3 kỳ gần nhất, loại bỏ tháng Tết**

**GXT (HAN + SGN):**
- METATRUCK = 100% − DN (tệp còn lại đều = 0)

### 7.4 Constraint bắt buộc
```
Σ FC Comp (tất cả subsegment) = FC Raw volume (theo ngày/tuần/tháng)
Sai lệch = 0, không chấp nhận
```

---

## 8. Công thức tính Active

```
FC Active = CEILING(FC Comp / FC Prod)
Historical Active = pivot từ raw history (không tính, lấy thẳng)
```

---

## 9. Build approach

| Region | Build |
|--------|-------|
| HAN | Độc lập — input HAN, output HAN |
| SGN | Độc lập — input SGN, output SGN |

Không trộn data HAN/SGN ở bất kỳ bước nào.
