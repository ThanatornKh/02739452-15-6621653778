"""หน้าสถานะ pipeline — อ่านจากตารางที่ DAG บันทึกไว้ทุกรอบ"""

import pandas as pd
import streamlit as st

from db import query

st.set_page_config(page_title="Pipeline Status", page_icon="🛠️", layout="wide")
st.title("🛠️ สถานะ Pipeline")

STATUS_ICON = {"SUCCESS": "🟢", "PARTIAL": "🟡", "DQ_FAILED": "🟠", "FAILED": "🔴"}

runs = query(
    """
    SELECT run_id, started_at, finished_at, status, sources_ok, sources_failed,
           raw_rows, unified_rows, dq_passed, branch
    FROM pipeline_runs ORDER BY finished_at DESC LIMIT 30
    """
)
if runs.empty:
    st.info("ยังไม่มีประวัติการรัน — รอ DAG `fx_multi_source_dag` รันรอบแรก")
    st.stop()

latest = runs.iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("สถานะรอบล่าสุด", f"{STATUS_ICON.get(latest['status'], '⚪')} {latest['status']}")
c2.metric("รันเสร็จเมื่อ", pd.Timestamp(latest["finished_at"]).tz_convert("Asia/Bangkok")
          .strftime("%d %b %Y %H:%M"))
c3.metric("แหล่งที่ใช้ได้", latest["sources_ok"] or "-")
c4.metric("แหล่งที่ล่ม", latest["sources_failed"] or "ไม่มี")

st.caption("🟢 SUCCESS ครบทุกแหล่ง · 🟡 PARTIAL บางแหล่งล่มแต่รวมจากที่เหลือได้ · "
           "🟠 DQ_FAILED ไม่ผ่านตรวจคุณภาพ (dashboard ไม่ถูกอัปเดต) · 🔴 FAILED")

st.subheader("ผลตรวจคุณภาพข้อมูล (รอบล่าสุด)")
dq = query(
    "SELECT check_name, passed, detail FROM dq_results WHERE run_id = %s ORDER BY check_name",
    (latest["run_id"],),
)
if not dq.empty:
    dq["ผล"] = dq["passed"].map({True: "✅ ผ่าน", False: "❌ ไม่ผ่าน"})
    st.dataframe(dq[["check_name", "ผล", "detail"]], hide_index=True, use_container_width=True)

st.subheader("แหล่งข้อมูลในแต่ละรอบ")
src = query(
    """
    SELECT s.run_id, r.finished_at, s.source, s.status, s.rows
    FROM source_runs s JOIN pipeline_runs r USING (run_id)
    ORDER BY r.finished_at DESC, s.source LIMIT 90
    """
)
if not src.empty:
    pivot = src.pivot_table(index=["finished_at", "run_id"], columns="source",
                            values="status", aggfunc="first").sort_index(ascending=False)
    st.dataframe(
        pivot.map(lambda v: "✅ success" if v == "success" else "❌ failed"),
        use_container_width=True,
    )

st.subheader("ประวัติการรัน")
runs["status"] = runs["status"].map(lambda s: f"{STATUS_ICON.get(s, '⚪')} {s}")
st.dataframe(runs, hide_index=True, use_container_width=True)

st.subheader("ข้อมูลดิบแยกตามแหล่ง")
per_src = query(
    """
    SELECT source, COUNT(*) AS rows, MIN(rate_date) AS first_date, MAX(rate_date) AS last_date,
           MAX(fetched_at) AS last_fetched
    FROM fx_rates_raw GROUP BY source ORDER BY source
    """
)
st.dataframe(per_src, hide_index=True, use_container_width=True)

quarantine = query(
    """
    SELECT run_id, rate_date, quote, rate, spread_pct, sources, reason
    FROM fx_rates_quarantine ORDER BY run_id DESC, rate_date DESC LIMIT 200
    """
)
if not quarantine.empty:
    st.subheader("แถวที่ถูกกักไว้ (ไม่ผ่าน quality check)")
    st.dataframe(quarantine, hide_index=True, use_container_width=True)
