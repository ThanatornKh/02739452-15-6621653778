"""FX Multi-Source Dashboard — หน้าหลัก (ตาราง + กราฟ + KPI + ตัวกรอง)"""

from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

from db import QUOTE_INFO, query, thb_per_unit, unit_label
from style import apply_style, hero, section, style_chart

# ล็อกสีของแต่ละเส้นให้เหมือนเดิมเสมอ ไม่ขึ้นกับธีม/ลำดับข้อมูล
QUOTE_COLORS = alt.Scale(domain=["1 EUR", "1 USD", "1,000 KRW", "100 JPY"],
                         range=["#0068c9", "#83c9ff", "#ff2b2b", "#ffabab"])
SOURCE_COLORS = alt.Scale(domain=["frankfurter", "xrates", "yahoo"],
                          range=["#0068c9", "#83c9ff", "#ff2b2b"])

st.set_page_config(page_title="FX Multi-Source", layout="wide")
apply_style()
hero(
    "FX Multi-Source · 02739452",
    "Thai Baht <em>/</em> JPY · USD · EUR · KRW",
    "รวมอัตราแลกเปลี่ยนจาก 3 แหล่ง — Frankfurter API (ECB), Yahoo Finance และ x-rates.com "
    "(web scraping) ประมวลผลด้วย Apache Airflow แล้วอ่านตรงจาก PostgreSQL",
)

data = query(
    """
    SELECT rate_date, quote, rate, rate_min, rate_max, spread_pct,
           source_count, sources, updated_at
    FROM fx_rates_published
    ORDER BY rate_date, quote
    """
)
if data.empty:
    st.info("ยังไม่มีข้อมูล — รอ DAG `fx_multi_source_dag` รันรอบแรกให้เสร็จ (ประมาณ 2-3 นาที) "
            "แล้วกดรีเฟรชหน้านี้")
    if err := st.session_state.get("db_error"):
        st.caption(f"รายละเอียด: {err}")
    st.stop()

data["rate_date"] = pd.to_datetime(data["rate_date"])
data["thb"] = thb_per_unit(data)
data["unit"] = data["quote"].map(unit_label)

# ---------------------------- ตัวกรอง ----------------------------
min_d, max_d = data["rate_date"].min().date(), data["rate_date"].max().date()
with st.sidebar:
    st.header("Filters")
    quotes = st.multiselect(
        "สกุลเงิน", list(QUOTE_INFO), default=list(QUOTE_INFO),
        format_func=lambda q: f"{q}  ·  {QUOTE_INFO[q]['name']}",
    )
    preset = st.radio("ช่วงเวลา", ["1 เดือน", "6 เดือน", "1 ปี", "ทั้งหมด", "กำหนดเอง"],
                      index=2, horizontal=True)
    days = {"1 เดือน": 31, "6 เดือน": 183, "1 ปี": 366}.get(preset)
    if preset == "กำหนดเอง":
        picked = st.date_input("วันที่", (max_d - timedelta(days=90), max_d),
                               min_value=min_d, max_value=max_d)
        start, end = (picked[0], picked[-1]) if len(picked) else (min_d, max_d)
    else:
        start, end = (max_d - timedelta(days=days) if days else min_d), max_d
    min_sources = st.slider("จำนวนแหล่งที่ยืนยันขั้นต่ำ", 1, 3, 1,
                            help="แสดงเฉพาะวันที่มีข้อมูลจากอย่างน้อย N แหล่ง")

if not quotes:
    st.warning("เลือกสกุลเงินอย่างน้อย 1 สกุล")
    st.stop()

mask = (
    data["quote"].isin(quotes)
    & data["rate_date"].dt.date.between(start, end)
    & (data["source_count"] >= min_sources)
)
view = data[mask]

# ---------------------------- KPI ----------------------------
section("01", "Overview", f"ล่าสุด {data['rate_date'].max():%d %b %Y} · บาทต่อหน่วย · เทียบ 7 วันก่อน "
        "(สีแดง = เงินต่างประเทศแพงขึ้น)")
cols = st.columns(len(quotes))
for col, q in zip(cols, quotes):
    s = data[data["quote"] == q].sort_values("rate_date")
    if s.empty:
        continue
    last = s.iloc[-1]
    prev = s[s["rate_date"] <= last["rate_date"] - timedelta(days=7)]
    delta = None
    if not prev.empty:
        delta = (last["thb"] / prev.iloc[-1]["thb"] - 1) * 100
    col.metric(
        f"{unit_label(q)} · THB",
        f"{last['thb']:,.2f}",
        f"{delta:+.2f}%" if delta is not None else None,
        delta_color="inverse",  # บาทต่อหน่วยลดลง = เงินต่างประเทศถูกลง = สีเขียว
    )

k1, k2, k3, k4 = st.columns(4)
raw_total = query("SELECT COUNT(*) AS n FROM fx_rates_raw")
k1.metric("Rows shown", f"{len(view):,}")
k2.metric("Unified rows", f"{len(data):,}")
k3.metric("Raw rows · 3 sources", f"{int(raw_total['n'].iloc[0]):,}" if not raw_total.empty else "-")
k4.metric("Avg source spread",
          f"{view['spread_pct'].mean():.3f}%" if not view.empty else "-")

# ---------------------------- กราฟ ----------------------------
section("02", "Price Trend", "บาทต่อหน่วย")
if view.empty:
    st.info("ไม่มีข้อมูลตรงกับตัวกรอง")
else:
    normalize = st.toggle("แสดงเป็น % เปลี่ยนแปลงจากวันแรกของช่วง (เทียบหลายสกุลบนกราฟเดียว)",
                          value=len(quotes) > 1)
    chart_df = view[["rate_date", "quote", "unit", "thb"]].copy()
    if normalize:
        first = chart_df.sort_values("rate_date").groupby("quote")["thb"].transform("first")
        chart_df["value"] = (chart_df["thb"] / first - 1) * 100
        y_title = "% เปลี่ยนแปลง"
    else:
        chart_df["value"] = chart_df["thb"]
        y_title = "บาท"
    chart = (
        alt.Chart(chart_df)
        .mark_line(strokeWidth=1.8)
        .encode(
            x=alt.X("rate_date:T", title="วันที่"),
            y=alt.Y("value:Q", title=y_title, scale=alt.Scale(zero=False)),
            color=alt.Color("unit:N", title="สกุล", scale=QUOTE_COLORS),
            tooltip=[alt.Tooltip("rate_date:T", title="วันที่"),
                     alt.Tooltip("unit:N", title="สกุล"),
                     alt.Tooltip("thb:Q", title="บาท", format=",.4f")],
        )
        .properties(height=380)
        .interactive()
    )
    st.altair_chart(style_chart(chart), use_container_width=True, theme=None)

# ------------------ เปรียบเทียบรายแหล่ง (จากตาราง raw) ------------------
section("03", "Source Comparison", "ราคาเดียวกันจากแต่ละแหล่ง")
q_cmp = st.selectbox("สกุล", quotes, format_func=unit_label, key="cmp")
raw = query(
    """
    SELECT source, rate_date, quote, rate FROM fx_rates_raw
    WHERE quote = %s AND rate_date BETWEEN %s AND %s
    ORDER BY rate_date
    """,
    (q_cmp, max(start, end - timedelta(days=60)), end),
)
if not raw.empty:
    raw["rate_date"] = pd.to_datetime(raw["rate_date"])
    raw["thb"] = thb_per_unit(raw)
    st.altair_chart(
        style_chart(alt.Chart(raw)
        .mark_line(point=True, strokeWidth=1.5)
        .encode(
            x=alt.X("rate_date:T", title="วันที่"),
            y=alt.Y("thb:Q", title=f"บาทต่อ {unit_label(q_cmp)}", scale=alt.Scale(zero=False)),
            color=alt.Color("source:N", title="แหล่ง", scale=SOURCE_COLORS),
            tooltip=["source", alt.Tooltip("rate_date:T"), alt.Tooltip("thb:Q", format=",.4f")],
        )
        .properties(height=300)
        .interactive()),
        use_container_width=True,
        theme=None,
    )
    st.caption("แสดงไม่เกิน 60 วันล่าสุดของช่วงที่เลือก (x-rates.com ดึงย้อนหลังเฉพาะช่วงสั้น)")

# ---------------------------- ตาราง ----------------------------
section("04", "Unified Dataset", "หลังรวมและตัดรายการซ้ำข้ามแหล่ง")
table = view.sort_values(["rate_date", "quote"], ascending=[False, True])[
    ["rate_date", "quote", "unit", "thb", "rate", "spread_pct", "source_count", "sources"]
].rename(columns={
    "rate_date": "วันที่", "quote": "สกุล", "unit": "หน่วย", "thb": "บาท",
    "rate": "1 THB =", "spread_pct": "ต่างกันระหว่างแหล่ง (%)",
    "source_count": "จำนวนแหล่ง", "sources": "แหล่ง",
})
st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
    column_config={
        "วันที่": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "บาท": st.column_config.NumberColumn(format="%.4f"),
        "1 THB =": st.column_config.NumberColumn(format="%.6f"),
        "ต่างกันระหว่างแหล่ง (%)": st.column_config.NumberColumn(format="%.3f"),
    },
)
st.download_button("ดาวน์โหลด CSV", table.to_csv(index=False).encode("utf-8-sig"),
                   "fx_rates.csv", "text/csv")
