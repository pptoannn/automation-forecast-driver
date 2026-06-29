# Automation Forecast Driver — Project Flow

> Cập nhật: 2026-06-28 | Version: v0.1

---

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    DRIVER SUPPLY FORECAST
                     Full Project Flow
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

─────────────────────────────────────────
  TẦNG 1 — DATA SOURCES
─────────────────────────────────────────

  ┌─────────────────┐     ┌──────────────────────────────┐
  │   SHEET A       │     │  METABASE (lịch sử tài xế)   │
  │  (Raw Input)    │     │                              │
  │  Bạn paste vào  │     │  Make kéo về định kỳ         │
  └────────┬────────┘     └──────────────┬───────────────┘
           │                             │
           │                    ┌────────▼──────────┐
           │                    │  Sheet: STAGING   │
           │                    │  (History buffer) │
           │                    └────────┬──────────┘
           │                             │
─────────────────────────────────────────────────────────────
  TẦNG 2 — PROCESSING  (Google Apps Script)
─────────────────────────────────────────────────────────────
           │                             │
           └──────────────┬──────────────┘
                          │
              ┌───────────▼────────────────────┐
              │         forecast.gs             │
              │  • CV method selection          │
              │  • FORECAST compute             │
              │  • Flag bất thường              │
              └───────────┬────────────────────┘
                          │
              ┌───────────▼────────────────────┐
              │         ai_agent.gs             │
              │  • Gọi Claude API               │
              │  • Đọc context + flags          │
              │  • Adhoc reasoning theo ý bạn   │
              │  • Output: keep / override +    │
              │    lý do + confidence           │
              └───────────┬────────────────────┘
                          │
              ┌───────────▼────────────────────┐
              │      Sheet: OVERRIDES           │
              │  • Ghi log mọi quyết định AI    │
              │  • Bạn có thể sửa tay ở đây    │
              └───────────┬────────────────────┘

─────────────────────────────────────────
  TẦNG 3 — 2-STEP OUTPUT
─────────────────────────────────────────

                          │
                 [Bạn bấm: 🚀 Generate Preview]
                          │
              ┌───────────▼────────────────────┐
              │      Sheet: PREVIEW / DEMO      │
              │  Kết quả đầy đủ, chưa final    │
              │  Bạn review, sửa tay nếu cần   │
              └───────────┬────────────────────┘
                          │
                 [Bạn bấm: ✅ Confirm & Push]
                          │
           ┌──────────────┴──────────────┐
           │                             │
  ┌────────▼──────────┐       ┌──────────▼────────┐
  │  Sheet: OPS VIEW  │       │ Sheet: EXEC VIEW  │
  │  Ops / Planning   │       │  Board / Exec     │
  │  Chi tiết:        │       │  Tổng hợp:        │
  │  Service × Region │       │  Tháng + vs Target│
  │  × Tuần           │       │  Traffic light    │
  └───────────────────┘       └───────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BUILD APPROACH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Phase 1  →  Python/Streamlit prototype local
               (iterate logic nhanh, thấy output ngay)

  Phase 2  →  Translate sang Google Apps Script
               (production, chạy thẳng trong Sheets)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CÁC FILE TRONG SPREADSHEET
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [INPUT]   Raw A          ← bạn paste data vào
  [DATA]    Staging        ← Make đổ Metabase về đây
  [CONFIG]  Overrides      ← log AI + sửa tay adhoc
  [PREVIEW] Demo           ← xem trước, chưa final
  [OUTPUT]  Ops View       ← final sheet 1
  [OUTPUT]  Exec View      ← final sheet 2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BUILD STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Phase 1  →  ✅ Project setup + GitHub
  Phase 2  →  ✅ Đọc Sheet + hiểu data structure + document logic (LOGIC.md)
  Phase 3  →  🔄 Build forecast engine (CV + LinReg + MA) — HAN trước
  Phase 4  →  ⏳ Build SGN (tương tự HAN, khác subsegment + residual rule)
  Phase 5  →  ⏳ AI Agent adhoc (ai_agent.py via n8n OpenAI)
  Phase 6  →  ⏳ Streamlit UI (upload → preview → confirm → push output)
  Phase 7  →  ⏳ Deploy Streamlit Cloud (public link)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STACK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Language  : Python
  UI        : Streamlit
  AI Model  : Claude Sonnet (Anthropic API)
  Data In   : Google Sheets (Sheet A) + Metabase via Make
  Data Out  : Google Sheets (Ops View + Exec View)
  Hosting   : Streamlit Community Cloud (free)
  GitHub    : github.com/pptoannn/automation-forecast-driver
```
