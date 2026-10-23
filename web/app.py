"""FX Multi-Source Dashboard — หน้าหลัก (ตาราง + กราฟ + KPI + ตัวกรอง)"""

from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

from db import QUOTE_INFO, query, thb_per_unit, unit_label

st.set_page_config(page_title="FX Multi-Source Dashboard", page_icon="💱", layout="wide")

st.title("💱 ค่าเงินบาทเทียบ JPY / USD / EUR / KRW")
st.caption(
    "รวมจาก 3 แหล่ง: Frankfurter API (ECB) · Yahoo Finance · x-rates.com (web scraping) "
    "— ประมวลผลด้วย Apache Airflow แล้วอ่านตรงจาก PostgreSQL"
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
    st.header("ตัวกรอง")
    quotes = st.multiselect(
        "สกุลเงิน", list(QUOTE_INFO), default=list(QUOTE_INFO),
        format_func=lambda q: f"{q} — {QUOTE_INFO[q]['name']}",
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
st.subheader("ภาพรวม")
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
        f"{unit_label(q)} ({last['rate_date']:%d %b %Y})",
        f"{last['thb']:,.2f} บาท",
        f"{delta:+.2f}% จาก 7 วันก่อน" if delta is not None else None,
        delta_color="inverse",  # บาทต่อหน่วยลดลง = เงินต่างประเทศถูกลง = สีเขียว
    )

k1, k2, k3, k4 = st.columns(4)
raw_total = query("SELECT COUNT(*) AS n FROM fx_rates_raw")
k1.metric("แถวที่แสดง (หลังกรอง)", f"{len(view):,}")
k2.metric("ข้อมูลรวมหลังตัดซ้ำ", f"{len(data):,}")
k3.metric("ข้อมูลดิบทุกแหล่ง", f"{int(raw_total['n'].iloc[0]):,}" if not raw_total.empty else "-")
k4.metric("ความต่างระหว่างแหล่ง (เฉลี่ย)",
          f"{view['spread_pct'].mean():.3f}%" if not view.empty else "-")

# ---------------------------- กราฟ ----------------------------
st.subheader("แนวโน้มราคา (บาทต่อหน่วย)")
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
            color=alt.Color("unit:N", title="สกุล"),
            tooltip=[alt.Tooltip("rate_date:T", title="วันที่"),
                     alt.Tooltip("unit:N", title="สกุล"),
                     alt.Tooltip("thb:Q", title="บาท", format=",.4f")],
        )
        .properties(height=380)
        .interactive()
    )
    st.altair_chart(chart, use_container_width=True)

# ------------------ เปรียบเทียบรายแหล่ง (จากตาราง raw) ------------------
st.subheader("เทียบราคาจากแต่ละแหล่ง")
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
        alt.Chart(raw)
        .mark_line(point=True, strokeWidth=1.5)
        .encode(
            x=alt.X("rate_date:T", title="วันที่"),
            y=alt.Y("thb:Q", title=f"บาทต่อ {unit_label(q_cmp)}", scale=alt.Scale(zero=False)),
            color=alt.Color("source:N", title="แหล่ง"),
            tooltip=["source", alt.Tooltip("rate_date:T"), alt.Tooltip("thb:Q", format=",.4f")],
        )
        .properties(height=300)
        .interactive(),
        use_container_width=True,
    )
    st.caption("แสดงไม่เกิน 60 วันล่าสุดของช่วงที่เลือก (x-rates.com ดึงย้อนหลังเฉพาะช่วงสั้น)")

# ---------------------------- ตาราง ----------------------------
st.subheader("ตารางข้อมูล (หลังรวมและตัดรายการซ้ำข้ามแหล่ง)")
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
