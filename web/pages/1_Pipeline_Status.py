"""หน้าสถานะ pipeline — อ่านจากตารางที่ DAG บันทึกไว้ทุกรอบ"""

import pandas as pd
import streamlit as st

from db import query
from style import apply_style, color_status, hero, kv, section, status_badge

st.set_page_config(page_title="Pipeline Status", layout="wide")
apply_style()
hero(
    "FX Multi-Source · Pipeline",
    "Pipeline <em>/</em> Status",
    "สถานะการรันของ DAG fx_multi_source_dag แหล่งข้อมูลที่ใช้ได้ในแต่ละรอบ และผลตรวจคุณภาพข้อมูล",
)

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

for col in ["started_at", "finished_at"]:
    runs[col] = pd.to_datetime(runs[col], utc=True).dt.tz_convert("Asia/Bangkok").dt.strftime("%Y-%m-%d %H:%M:%S")
latest = runs.iloc[0]
finished = pd.Timestamp(latest["finished_at"])

section("01", "Latest Run", latest["run_id"])
c1, c2, c3, c4 = st.columns(4)
c1.markdown(kv("Status", status_badge(latest["status"])), unsafe_allow_html=True)
c2.markdown(kv("Finished", finished.strftime("%d %b %Y · %H:%M")), unsafe_allow_html=True)
c3.markdown(kv("Sources OK", latest["sources_ok"] or "-"), unsafe_allow_html=True)
c4.markdown(kv("Sources Down", latest["sources_failed"] or "none"), unsafe_allow_html=True)
st.write("")
st.markdown(
    " &nbsp;&nbsp; ".join(status_badge(s) for s in ["SUCCESS", "PARTIAL", "DQ_FAILED", "FAILED"]),
    unsafe_allow_html=True,
)
st.caption("SUCCESS ครบทุกแหล่ง · PARTIAL บางแหล่งล่มแต่รวมจากที่เหลือได้ · "
           "DQ_FAILED ไม่ผ่านตรวจคุณภาพ (dashboard ไม่ถูกอัปเดต) · FAILED")

section("02", "Data Quality", "ผลตรวจรอบล่าสุด")
dq = query(
    "SELECT check_name, passed, detail FROM dq_results WHERE run_id = %s ORDER BY check_name",
    (latest["run_id"],),
)
if not dq.empty:
    dq["result"] = dq["passed"].map({True: "PASS", False: "FAIL"})
    st.dataframe(dq[["check_name", "result", "detail"]].style.map(color_status, subset=["result"]),
                 hide_index=True, use_container_width=True)

section("03", "Sources per Run")
src = query(
    """
    SELECT s.run_id, r.finished_at, s.source, s.status, s.rows
    FROM source_runs s JOIN pipeline_runs r USING (run_id)
    ORDER BY r.finished_at DESC, s.source LIMIT 90
    """
)
if not src.empty:
    src["finished_at"] = (pd.to_datetime(src["finished_at"], utc=True)
                          .dt.tz_convert("Asia/Bangkok").dt.strftime("%Y-%m-%d %H:%M:%S"))
    pivot = (src.pivot_table(index=["finished_at", "run_id"], columns="source",
                             values="status", aggfunc="first")
             .sort_index(ascending=False).reset_index())
    st.dataframe(pivot.style.map(color_status), hide_index=True, use_container_width=True)

section("04", "Run History")
st.dataframe(runs.style.map(color_status, subset=["status"]),
             hide_index=True, use_container_width=True)

section("05", "Raw Data by Source")
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
    section("06", "Quarantine", "แถวที่ไม่ผ่าน quality check")
    st.dataframe(quarantine, hide_index=True, use_container_width=True)
