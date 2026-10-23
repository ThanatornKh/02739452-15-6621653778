"""FX Multi-Source Dashboard — หน้าหลัก (ตาราง + กราฟ + KPI + ตัวกรอง)"""

import calendar
from datetime import date, timedelta

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
MONTHS_TH = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
             "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def line_chart(df, series, scale, y_title, height, split=False, points=False, focus_day=None):
    """กราฟเส้น: กด legend เพื่อเลือกดูทีละเส้น (Shift + คลิก เลือกหลายเส้น), ลาก/ซูมได้
    split=True แยกเป็นกราฟย่อยละ 1 เส้น, focus_day = วันที่ค้นหา (เส้นประ + จุดของวันนั้น)"""

    # แกนวันที่ใช้สตริง YYYY-MM-DD + สเกล UTC ทุก layer -> ตำแหน่งตรงกันและวันที่ในกล่องอ่านง่าย
    x_enc = alt.X("วันที่:T", title="วันที่", scale=alt.Scale(type="utc"))

    def build(d, h, with_legend_select):
        sel = alt.selection_point(fields=[series], bind="legend")
        # เส้นเล็ง: ชี้ตรงไหนก็จับวันที่ใกล้ที่สุด แล้วโชว์ค่าในวันนั้นในกล่องเดียว
        hover = alt.selection_point(fields=["วันที่"], nearest=True, on="pointerover",
                                    clear="pointerout", empty=False)
        d = pd.DataFrame({
            "วันที่": d["rate_date"].dt.strftime("%Y-%m-%d"),
            series: d[series],
            "value": d["value"],
            "_label": d[series] + " (บาท)",
            "_thb": d["thb"].round(4),
        })
        base = alt.Chart(d).encode(
            x=x_enc,
            y=alt.Y("value:Q", title=y_title, scale=alt.Scale(zero=False)),
            # สัญลักษณ์ legend คงแบบเดิม (ขีดสำหรับกราฟเส้นล้วน, วงกลมสำหรับกราฟที่มีจุด)
            color=alt.Color(f"{series}:N", title="", scale=scale,
                            legend=alt.Legend(symbolType="circle" if points else "stroke")),
        )
        line = base.mark_line(strokeWidth=1.8, point=points)
        hover_dots = base.mark_point(size=70, filled=True, stroke="white", strokeWidth=1).encode(
            opacity=alt.condition(hover, alt.value(1), alt.value(0)))
        tip_data = alt.Chart(d)
        if with_legend_select:
            line = line.encode(opacity=alt.condition(sel, alt.value(1), alt.value(0.08))).add_params(sel)
            # เลือกเส้นใน legend แล้ว -> จุดและกล่องข้อมูลแสดงเฉพาะเส้นที่เลือก
            hover_dots = hover_dots.transform_filter(sel)
            tip_data = tip_data.transform_filter(sel)
        # pivot: 1 แถวต่อวัน มีคอลัมน์เฉพาะเส้นที่ผ่าน filter -> เส้นที่ไม่ได้เลือกเป็น undefined
        # และไม่ถูกแสดงในกล่อง (title = หัวกล่องเป็นวันที่)
        names = [n for n in scale.domain if n in set(d[series])]
        keys = {f"{n} (บาท)": f"s{i}" for i, n in enumerate(names)}  # ชื่อคอลัมน์ปลอดภัย
        tip_data = tip_data.transform_calculate(_key=" + ".join(
            [f"(datum._label == '{lb}' ? '{k}' : '')" for lb, k in keys.items()]))
        # กล่องข้อมูลเป็น object: 'title' = หัวกล่อง (วันที่), เส้นที่ไม่ได้เลือกมีค่า undefined
        # ซึ่ง vega-tooltip ข้ามไปเอง -> กล่องแสดงเฉพาะเส้นที่เลือก
        tip_obj = "{'title': utcFormat(datum['วันที่'], '%d %b %Y')" + "".join(
            f", '{lb}': isValid(datum['{k}']) ? format(datum['{k}'], ',.4f') : datum['{k}']"
            for lb, k in keys.items()) + "}"
        crosshair = (
            tip_data.transform_pivot("_key", value="_thb", groupby=["วันที่"])
            .transform_calculate(_tip=tip_obj)
            .mark_rule(color="#8a8a8a", strokeWidth=1)
            .encode(x=x_enc, opacity=alt.condition(hover, alt.value(0.9), alt.value(0)),
                    tooltip=alt.Tooltip("_tip:N"))
            .add_params(hover)
        )
        layers = [line.interactive(), hover_dots, crosshair]
        if focus_day is not None:
            day = pd.Timestamp(focus_day).strftime("%Y-%m-%d")
            rule = alt.Chart(pd.DataFrame({"วันที่": [day]})).mark_rule(
                color="#d0021b", strokeDash=[5, 4], strokeWidth=1.5).encode(x=x_enc)
            dots = alt.Chart(d[d["วันที่"] == day]).mark_point(
                size=110, filled=True, stroke="white", strokeWidth=1).encode(
                x=x_enc, y="value:Q", color=alt.Color(f"{series}:N", title="", scale=scale))
            layers += [rule, dots]
        return alt.layer(*layers).properties(height=h)

    if not split:
        return style_chart(build(df, height, True))
    names = [n for n in scale.domain if n in set(df[series])]
    rows = [build(df[df[series] == n], max(140, height // max(len(names), 1)), False)
            .properties(title=n) for n in names]
    return style_chart(alt.vconcat(*rows).resolve_scale(x="shared"))


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

    st.header("Search")
    years = sorted(data["rate_date"].dt.year.unique().tolist(), reverse=True)
    # เปิดลิงก์แบบ ?year=2024&month=8&day=5 แล้วค้นหาให้ทันที (แชร์ลิงก์ได้)
    for key, param, choices in [("f_year", "year", years), ("f_month", "month", range(1, 13)),
                                ("f_day", "day", range(1, 32))]:
        value = st.query_params.get(param)
        if key not in st.session_state and value and value.isdigit() and int(value) in choices:
            st.session_state[key] = int(value)
    def _on_year():
        # เลือกปี "ทั้งหมด" -> ล้างเดือนและวันด้วย ไม่ให้ค่าเก่าค้างอยู่
        if st.session_state["f_year"] == "ทั้งหมด":
            st.session_state["f_month"] = "ทั้งหมด"
            st.session_state["f_day"] = "ทั้งหมด"

    def _on_month():
        if st.session_state["f_month"] == "ทั้งหมด":
            st.session_state["f_day"] = "ทั้งหมด"

    f_year = st.selectbox("ปี", ["ทั้งหมด", *years], key="f_year", on_change=_on_year)
    f_month = st.selectbox("เดือน", ["ทั้งหมด", *range(1, 13)], key="f_month", on_change=_on_month,
                           format_func=lambda m: m if m == "ทั้งหมด" else MONTHS_TH[m - 1],
                           disabled=f_year == "ทั้งหมด")
    n_days = (calendar.monthrange(int(f_year), int(f_month))[1]
              if "ทั้งหมด" not in (f_year, f_month) else 31)
    # เปลี่ยนเดือนแล้ววันเดิมเกินจำนวนวันของเดือนใหม่ (เช่น 31 -> ก.พ.) -> กลับเป็น "ทั้งหมด"
    if isinstance(st.session_state.get("f_day"), int) and st.session_state["f_day"] > n_days:
        st.session_state["f_day"] = "ทั้งหมด"
    f_day = st.selectbox("วัน", ["ทั้งหมด", *range(1, n_days + 1)], key="f_day",
                         disabled=f_year == "ทั้งหมด" or f_month == "ทั้งหมด")

# ค้นหา ปี/เดือน/วัน -> ซูมกราฟและตารางไปที่ช่วงนั้น (แทนที่ "ช่วงเวลา" ด้านบน)
focus_day, focus_label = None, None
if f_year != "ทั้งหมด":
    y = int(f_year)
    if f_month == "ทั้งหมด":
        start, end = date(y, 1, 1), date(y, 12, 31)
        focus_label = f"ปี {y}"
    elif f_day == "ทั้งหมด":
        m = int(f_month)
        start, end = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
        focus_label = f"{MONTHS_TH[m - 1]} {y}"
    else:
        focus_day = date(y, int(f_month), int(f_day))
        start, end = focus_day - timedelta(days=10), focus_day + timedelta(days=10)
        focus_label = f"{focus_day:%d} {MONTHS_TH[focus_day.month - 1]} {y} (±10 วัน)"
    start, end = max(start, min_d), min(end, max_d)

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
section("02", "Price Trend", f"โฟกัส {focus_label}" if focus_label else "บาทต่อหน่วย")
if focus_label:
    st.caption(f"กำลังซูมไปที่ {focus_label} — ล้างการค้นหาได้ที่ Search ด้านซ้าย (เลือก 'ทั้งหมด')")
if view.empty:
    st.info("ไม่มีข้อมูลตรงกับตัวกรอง")
else:
    c1, c2 = st.columns(2)
    normalize = c1.toggle("แสดงเป็น % เปลี่ยนแปลงจากวันแรกของช่วง",
                          value=len(quotes) > 1 and focus_day is None)
    split_trend = c2.toggle("แยกเส้นเป็นกราฟย่อยรายสกุล", key="split_trend")
    chart_df = view[["rate_date", "quote", "unit", "thb"]].copy()
    if normalize:
        first = chart_df.sort_values("rate_date").groupby("quote")["thb"].transform("first")
        chart_df["value"] = (chart_df["thb"] / first - 1) * 100
        y_title = "% เปลี่ยนแปลง"
    else:
        chart_df["value"] = chart_df["thb"]
        y_title = "บาท"
    st.altair_chart(
        line_chart(chart_df, "unit", QUOTE_COLORS, y_title, 380, split=split_trend,
                   points=focus_day is not None, focus_day=focus_day),
        use_container_width=True, theme=None,
    )
    st.caption("ชี้เมาส์ที่กราฟเพื่อดูค่าในวันนั้น (เลือกเส้นใน legend แล้วจะแสดงเฉพาะเส้นที่เลือก) · กดชื่อในคำอธิบายสีเพื่อแยกดูทีละเส้น (Shift + คลิก เลือกหลายเส้น, คลิกที่ว่างเพื่อแสดงทั้งหมด) · "
               "ลากเพื่อเลื่อน · scroll เพื่อซูม · ดับเบิลคลิกเพื่อรีเซ็ต")

    if focus_day is not None:
        day_rows = (view[view["rate_date"].dt.date <= focus_day]
                    .sort_values("rate_date").groupby("quote").tail(1)
                    .set_index("quote").reindex([q for q in QUOTE_INFO if q in quotes])
                    .dropna(subset=["rate_date"]).reset_index())
        if not day_rows.empty:
            shown = day_rows["rate_date"].max().date()
            note = ("" if shown == focus_day else
                    f" — วันที่เลือกไม่มีเรต (วันหยุด) จึงแสดงวันทำการก่อนหน้า {shown:%d %b %Y}")
            st.markdown(f"**ข้อมูลวันที่ {focus_day:%d %b %Y}**{note}")
            cols = st.columns(len(day_rows))
            for col, (_, r) in zip(cols, day_rows.iterrows()):
                col.metric(f"{r['unit']} · THB", f"{r['thb']:,.4f}",
                           f"{r['source_count']} แหล่ง · ต่างกัน {r['spread_pct']:.2f}%",
                           delta_color="off")

# ------------------ เปรียบเทียบรายแหล่ง (จากตาราง raw) ------------------
section("03", "Source Comparison", "ราคาเดียวกันจากแต่ละแหล่ง")
c1, c2 = st.columns([2, 1])
q_cmp = c1.selectbox("สกุล", quotes, format_func=unit_label, key="cmp")
split_src = c2.toggle("แยกเส้นเป็นกราฟย่อยรายแหล่ง", key="split_src")
cmp_start = start if focus_label else max(start, end - timedelta(days=60))
raw = query(
    """
    SELECT source, rate_date, quote, rate FROM fx_rates_raw
    WHERE quote = %s AND rate_date BETWEEN %s AND %s
    ORDER BY rate_date
    """,
    (q_cmp, cmp_start, end),
)
if raw.empty:
    st.info("ไม่มีข้อมูลรายแหล่งในช่วงนี้")
else:
    raw["rate_date"] = pd.to_datetime(raw["rate_date"])
    raw["thb"] = thb_per_unit(raw)
    raw["value"] = raw["thb"]
    st.altair_chart(
        line_chart(raw, "source", SOURCE_COLORS, f"บาทต่อ {unit_label(q_cmp)}", 300,
                   split=split_src, points=True, focus_day=focus_day),
        use_container_width=True, theme=None,
    )
    st.caption(("ช่วงที่ค้นหา" if focus_label else "60 วันล่าสุดของช่วงที่เลือก")
               + " · x-rates.com มีข้อมูลเฉพาะ 30 วันล่าสุด · ชี้เมาส์เพื่อเทียบค่าทุกแหล่งในวันนั้น · กดชื่อแหล่งใน legend เพื่อแยกดูทีละเส้น")

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
