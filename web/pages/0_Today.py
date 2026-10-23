"""สรุปข้อมูลล่าสุดของวันนี้ — เรตล่าสุดของแต่ละสกุล, การเปลี่ยนแปลง และค่าจากแต่ละแหล่ง"""

from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

from db import QUOTE_INFO, query, thb_per_unit, unit_label
from style import apply_style, hero, kv, section, style_chart

QUOTE_COLORS = {"JPY": "#ffabab", "USD": "#83c9ff", "EUR": "#0068c9", "KRW": "#ff2b2b"}

st.set_page_config(page_title="Today", layout="wide")
apply_style()

data = query(
    """
    SELECT rate_date, quote, rate, spread_pct, source_count, sources
    FROM fx_rates_published
    WHERE rate_date >= (SELECT MAX(rate_date) FROM fx_rates_published) - 400
    ORDER BY rate_date
    """
)
if data.empty:
    hero("FX Multi-Source · Today", "Today", "ยังไม่มีข้อมูล — รอ DAG รันรอบแรก")
    st.stop()

data["rate_date"] = pd.to_datetime(data["rate_date"])
data["thb"] = thb_per_unit(data)
latest_day = data["rate_date"].max()
hero(
    "FX Multi-Source · Today",
    f"Today <em>/</em> {latest_day:%d %b %Y}",
    "สรุปเรตล่าสุดของแต่ละสกุล (บาทต่อหน่วย) เทียบกับวันทำการก่อนหน้าและ 7 วันก่อน "
    "พร้อมค่าจากแต่ละแหล่งของวันล่าสุด",
)

# -------------------- ถูกหรือแพงกว่าปกติ (เชิงข้อมูล ไม่ใช่คำแนะนำ) --------------------
section("01", "Cheap or Expensive vs Normal", "เทียบราคาวันนี้กับค่าเฉลี่ย 90 วัน และกรอบราคา 1 ปี")
rows = []
for q in QUOTE_INFO:
    s_q = data[data["quote"] == q].sort_values("rate_date")
    if len(s_q) < 20:
        continue
    now = s_q.iloc[-1]["thb"]
    last90 = s_q[s_q["rate_date"] >= latest_day - timedelta(days=90)]["thb"]
    year = s_q[s_q["rate_date"] >= latest_day - timedelta(days=365)]["thb"]
    rows.append({
        "unit": unit_label(q),
        "vs_avg90": (now / last90.mean() - 1) * 100,
        "pos_1y": (now - year.min()) / (year.max() - year.min()) * 100 if year.max() > year.min() else 50.0,
        "now": now, "avg90": last90.mean(), "min1y": year.min(), "max1y": year.max(),
    })
sig = pd.DataFrame(rows).sort_values("vs_avg90")
if not sig.empty:
    sig["label"] = sig["vs_avg90"].map(
        lambda v: f"ถูกกว่าค่าเฉลี่ย {abs(v):.2f}%" if v < 0 else f"แพงกว่าค่าเฉลี่ย {v:.2f}%")
    c1, c2 = st.columns(2)
    order = sig["unit"].tolist()
    bars = (
        alt.Chart(sig).mark_bar(size=26)
        .encode(
            y=alt.Y("unit:N", sort=order, title=""),
            x=alt.X("vs_avg90:Q", title="% เทียบค่าเฉลี่ย 90 วัน (ติดลบ = ถูกกว่าปกติ)"),
            color=alt.condition("datum.vs_avg90 < 0", alt.value("#2ecc71"), alt.value("#ff3b30")),
            tooltip=[alt.Tooltip("unit:N", title="สกุล"), alt.Tooltip("now:Q", title="วันนี้ (บาท)", format=",.4f"),
                     alt.Tooltip("avg90:Q", title="เฉลี่ย 90 วัน", format=",.4f"),
                     alt.Tooltip("label:N", title="สรุป")],
        )
    )
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#8a8a8a").encode(x="x:Q")
    c1.altair_chart(style_chart((bars + zero).properties(height=230,
                    title="เทียบค่าเฉลี่ย 90 วัน")), use_container_width=True, theme=None)

    pos = (
        alt.Chart(sig).mark_bar(size=26)
        .encode(
            y=alt.Y("unit:N", sort=order, title=""),
            x=alt.X("pos_1y:Q", title="ตำแหน่งในกรอบราคา 1 ปี (0 = ต่ำสุดของปี, 100 = สูงสุดของปี)",
                    scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("pos_1y:Q", legend=None,
                            scale=alt.Scale(domain=[0, 50, 100], range=["#2ecc71", "#f5c518", "#ff3b30"])),
            tooltip=[alt.Tooltip("unit:N", title="สกุล"),
                     alt.Tooltip("min1y:Q", title="ต่ำสุด 1 ปี", format=",.4f"),
                     alt.Tooltip("max1y:Q", title="สูงสุด 1 ปี", format=",.4f"),
                     alt.Tooltip("pos_1y:Q", title="ตำแหน่ง", format=".0f")],
        )
    )
    c2.altair_chart(style_chart(pos.properties(height=230, title="ตำแหน่งในกรอบราคา 1 ปี")),
                    use_container_width=True, theme=None)

    best = sig.iloc[0]
    st.markdown(
        f"**สรุปจากข้อมูล:** ตอนนี้ **{best['unit']}** ถูกกว่าค่าเฉลี่ย 90 วันมากที่สุดเมื่อเทียบกับสกุลอื่น "
        f"({best['label']}, อยู่ที่ระดับ {best['pos_1y']:.0f}% ของกรอบราคา 1 ปี) "
        "— เรียงจากถูกกว่าปกติมากที่สุดไปน้อยที่สุด: " + " › ".join(order)
    )
    st.caption("เป็นการสรุปเชิงสถิติจากข้อมูลย้อนหลังเท่านั้น ไม่ใช่คำแนะนำทางการเงิน "
               "อัตราในอนาคตอาจไม่เป็นไปตามค่าเฉลี่ยในอดีต และเรตจริงของร้านแลกเงินมีส่วนต่างซื้อ-ขาย")

# ---------------------------- การ์ดรายสกุล ----------------------------
section("02", "Latest Rates", "บาทต่อหน่วย · สีแดง = เงินต่างประเทศแพงขึ้น")
cols = st.columns(len(QUOTE_INFO))
for col, q in zip(cols, QUOTE_INFO):
    s = data[data["quote"] == q].sort_values("rate_date")
    if s.empty:
        continue
    last, prev = s.iloc[-1], (s.iloc[-2] if len(s) > 1 else None)
    week = s[s["rate_date"] <= last["rate_date"] - timedelta(days=7)]
    d1 = (last["thb"] / prev["thb"] - 1) * 100 if prev is not None else None
    d7 = (last["thb"] / week.iloc[-1]["thb"] - 1) * 100 if not week.empty else None
    month = s[s["rate_date"] >= last["rate_date"] - timedelta(days=30)]
    with col:
        st.metric(f"{unit_label(q)} · THB", f"{last['thb']:,.4f}",
                  f"{d1:+.2f}% จากวันก่อน" if d1 is not None else None, delta_color="inverse")
        st.markdown(
            kv("7 วัน", f"{d7:+.2f}%" if d7 is not None else "-")
            + kv("30 วัน ต่ำสุด / สูงสุด", f"{month['thb'].min():,.2f} / {month['thb'].max():,.2f}")
            + kv("แหล่งที่ยืนยัน", f"{int(last['source_count'])} · {last['sources']}"),
            unsafe_allow_html=True,
        )
        spark = (
            alt.Chart(month).mark_line(strokeWidth=2, color=QUOTE_COLORS[q])
            .encode(x=alt.X("rate_date:T", axis=None),
                    y=alt.Y("thb:Q", axis=None, scale=alt.Scale(zero=False)),
                    tooltip=[alt.Tooltip("rate_date:T", title="วันที่"),
                             alt.Tooltip("thb:Q", title="บาท", format=",.4f")])
            .properties(height=70)
        )
        st.altair_chart(style_chart(spark), use_container_width=True, theme=None)

# ---------------------------- ค่าจากแต่ละแหล่ง ----------------------------
section("03", "By Source", "ค่าล่าสุดที่แต่ละแหล่งรายงาน")
raw = query(
    """
    SELECT DISTINCT ON (source, quote) source, quote, rate_date, rate, fetched_at
    FROM fx_rates_raw
    ORDER BY source, quote, rate_date DESC
    """
)
if not raw.empty:
    raw["thb"] = thb_per_unit(raw)
    raw["cell"] = raw.apply(lambda r: f"{r['thb']:,.4f}  ({pd.Timestamp(r['rate_date']):%d %b})", axis=1)
    table = raw.pivot(index="source", columns="quote", values="cell")[list(QUOTE_INFO)]
    table.columns = [unit_label(q) for q in table.columns]
    st.dataframe(table, use_container_width=True)
    st.caption("ตัวเลข = บาทต่อหน่วย (วันที่ของเรตในวงเล็บ) · Yahoo Finance อาจมีเรตระหว่างวันของวันนี้ "
               "ส่วน Frankfurter (ECB) และ x-rates ประกาศหลังปิดวัน")

# ---------------------------- 10 วันทำการล่าสุด ----------------------------
section("04", "Last 10 Business Days", "บาทต่อหน่วย")
last10 = data[data["rate_date"] >= sorted(data["rate_date"].unique())[-10]]
grid = last10.pivot(index="rate_date", columns="quote", values="thb")[list(QUOTE_INFO)]
grid = grid.sort_index(ascending=False)
grid.index = grid.index.strftime("%Y-%m-%d (%a)")
grid.columns = [unit_label(q) for q in grid.columns]
st.dataframe(grid.style.format("{:,.4f}"), use_container_width=True)
