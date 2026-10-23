"""
fx_multi_source_dag
===================
รวมอัตราแลกเปลี่ยน "1 บาท (THB) = กี่ JPY / USD / EUR / KRW" จาก 3 แหล่ง
ให้เป็นชุดข้อมูลเดียวใน PostgreSQL แล้ว dashboard (web/) อ่านไปแสดง

แหล่งข้อมูล (แต่ละแหล่งอยู่ใน TaskGroup ของตัวเอง รันขนานกัน)
  1) Frankfurter API  — JSON, ข้อมูลอ้างอิงของ ECB, ย้อนหลัง 6 ปี
  2) Yahoo Finance    — JSON chart endpoint, ย้อนหลัง 6 ปี
  3) x-rates.com      — web scraping หน้า HTML (requests + BeautifulSoup, ไม่ใช้ Selenium)
                         robots.txt อนุญาตทุก path ยกเว้น /auth/
                         ดึงทีละวันด้วย Dynamic Task Mapping และหน่วงเวลาทุก request

ลำดับงาน
  create_tables
    -> [frankfurter | yahoo | xrates]   (TaskGroup, extract -> transform -> load_raw แบบ UPSERT)
    -> merge_dedup        trigger_rule=all_done: แหล่งไหนล่ม ก็รวมจากแหล่งที่เหลือต่อ
    -> quality_check      BranchPythonOperator
         ├─ ผ่าน    -> publish      (คัดลอกขึ้นตารางที่ dashboard ใช้)
         └─ ไม่ผ่าน -> quarantine   (ไม่แตะตาราง dashboard, เก็บแถวที่มีปัญหาไว้ตรวจ)
    -> record_run         บันทึกสถานะรอบนี้ (หน้า Pipeline Status บนเว็บอ่านจากตารางนี้)

ทดสอบกรณีแหล่งข้อมูลล่ม: Trigger DAG w/ config  {"simulate_down": "yahoo"}
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

import pendulum
import requests
from airflow import DAG
from airflow.decorators import task, task_group
from airflow.exceptions import AirflowFailException
from airflow.models.param import Param
from airflow.operators.empty import EmptyOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger(__name__)

CONN_ID = "postgres_target"
BASE = "THB"
QUOTES = ["JPY", "USD", "EUR", "KRW"]
HISTORY_YEARS = 6
SOURCES = ["frankfurter", "yahoo", "xrates"]

# ประกาศตัวตนชัดเจน (มารยาทกับเจ้าของเว็บ) — ไม่มีข้อมูลส่วนบุคคลใดๆ ถูกเก็บ
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; fx-multisource-student-project/1.0; "
    "+https://github.com/ThanatornKh/02739452-15-6621653778)"
}
XRATES_DELAY_SEC = 1.0

# เกณฑ์ตรวจคุณภาพข้อมูล
DQ_MIN_ROWS = 100
DQ_MAX_SPREAD_PCT = 2.0         # แหล่งต่างกันเกินกี่ % ถือว่า "ไม่ตรงกัน"
DQ_MAX_BAD_SPREAD_SHARE = 1.0   # ยอมให้แถวที่ไม่ตรงกันมีได้ไม่เกินกี่ % ของทั้งหมด
DQ_MAX_STALE_DAYS = 5

CREATE_TABLES_SQL = """
-- ข้อมูลดิบจากทุกแหล่ง schema เดียวกัน (PK มี source -> UPSERT รันซ้ำแถวไม่เพิ่ม)
CREATE TABLE IF NOT EXISTS fx_rates_raw (
    source      VARCHAR(20)      NOT NULL,
    rate_date   DATE             NOT NULL,
    base        VARCHAR(3)       NOT NULL,
    quote       VARCHAR(3)       NOT NULL,
    rate        DOUBLE PRECISION NOT NULL,
    fetched_at  TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, rate_date, base, quote)
);

-- รวมทุกแหล่ง + ตัดรายการซ้ำข้ามแหล่ง: 1 แถวต่อ (วัน, สกุล)
CREATE TABLE IF NOT EXISTS fx_rates (
    rate_date     DATE             NOT NULL,
    base          VARCHAR(3)       NOT NULL,
    quote         VARCHAR(3)       NOT NULL,
    rate          DOUBLE PRECISION NOT NULL,   -- ค่ามัธยฐานของทุกแหล่ง
    rate_min      DOUBLE PRECISION NOT NULL,
    rate_max      DOUBLE PRECISION NOT NULL,
    spread_pct    DOUBLE PRECISION NOT NULL,   -- (max-min)/median * 100
    source_count  INTEGER          NOT NULL,
    sources       VARCHAR(60)      NOT NULL,
    updated_at    TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rate_date, base, quote)
);

-- ตารางที่ dashboard อ่าน: อัปเดตเฉพาะรอบที่ผ่าน quality check
CREATE TABLE IF NOT EXISTS fx_rates_published (LIKE fx_rates INCLUDING ALL);

-- แถวที่ไม่ผ่าน quality check ของแต่ละรอบ
CREATE TABLE IF NOT EXISTS fx_rates_quarantine (
    run_id      VARCHAR(250) NOT NULL,
    rate_date   DATE         NOT NULL,
    quote       VARCHAR(3)   NOT NULL,
    rate        DOUBLE PRECISION,
    spread_pct  DOUBLE PRECISION,
    sources     VARCHAR(60),
    reason      VARCHAR(200) NOT NULL,
    PRIMARY KEY (run_id, rate_date, quote)
);

-- สถานะ pipeline สำหรับหน้า Pipeline Status
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id         VARCHAR(250) PRIMARY KEY,
    started_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ,
    status         VARCHAR(20),
    sources_ok     VARCHAR(60),
    sources_failed VARCHAR(60),
    raw_rows       INTEGER,
    unified_rows   INTEGER,
    dq_passed      BOOLEAN,
    branch         VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS source_runs (
    run_id   VARCHAR(250) NOT NULL,
    source   VARCHAR(20)  NOT NULL,
    status   VARCHAR(20)  NOT NULL,
    rows     INTEGER,
    PRIMARY KEY (run_id, source)
);

CREATE TABLE IF NOT EXISTS dq_results (
    run_id      VARCHAR(250) NOT NULL,
    check_name  VARCHAR(50)  NOT NULL,
    passed      BOOLEAN      NOT NULL,
    detail      VARCHAR(300),
    checked_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, check_name)
);
"""


# -----------------------------------------------------------------
# helpers
# -----------------------------------------------------------------
def _check_simulated_outage(source: str, context) -> None:
    """ให้ทดสอบกรณีแหล่งล่มได้จากหน้า Trigger DAG w/ config"""
    if context["params"].get("simulate_down") == source:
        raise AirflowFailException(f"[simulate_down] จำลองว่าแหล่ง {source} ล่ม")


def _http_get(url: str, **kwargs) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp


def _normalize(source: str, records: list[dict]) -> list[dict]:
    """transform: ทุกแหล่งออกมาเป็น schema เดียวกัน + ตัดค่าผิดรูป/ซ้ำในแหล่งเดียวกัน"""
    clean: dict[tuple, dict] = {}
    for r in records:
        quote = str(r["quote"]).upper().strip()
        try:
            rate = float(r["rate"])
        except (TypeError, ValueError):
            continue
        if quote not in QUOTES or not rate > 0:
            continue
        rate_date = str(r["rate_date"])[:10]
        clean[(rate_date, quote)] = {
            "source": source,
            "rate_date": rate_date,
            "base": BASE,
            "quote": quote,
            "rate": round(rate, 8),
        }
    rows = sorted(clean.values(), key=lambda x: (x["rate_date"], x["quote"]))
    log.info("%s: %d แถวดิบ -> %d แถวหลัง normalize", source, len(records), len(rows))
    return rows


def _upsert_raw(rows: list[dict]) -> int:
    if not rows:
        raise AirflowFailException("ไม่มีข้อมูลให้โหลด")
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    conn = hook.get_conn()
    with conn, conn.cursor() as cur:
        from psycopg2.extras import execute_values

        execute_values(
            cur,
            """
            INSERT INTO fx_rates_raw (source, rate_date, base, quote, rate, fetched_at)
            VALUES %s
            ON CONFLICT (source, rate_date, base, quote)
            DO UPDATE SET rate = EXCLUDED.rate, fetched_at = NOW()
            """,
            [(r["source"], r["rate_date"], r["base"], r["quote"], r["rate"]) for r in rows],
            template="(%s, %s, %s, %s, %s, NOW())",
            page_size=1000,
        )
    conn.close()
    log.info("UPSERT %d แถว (แหล่ง %s)", len(rows), rows[0]["source"])
    return len(rows)


# -----------------------------------------------------------------
# DAG
# -----------------------------------------------------------------
default_args = {
    "owner": "6621653778",
    "retries": 1,
    "retry_delay": timedelta(seconds=20),
}

with DAG(
    dag_id="fx_multi_source_dag",
    description="รวมเรต THB->JPY/USD/EUR/KRW จาก Frankfurter + Yahoo Finance + x-rates.com",
    default_args=default_args,
    schedule="0 7 * * *",  # ทุกวัน 07:00 เวลาไทย
    start_date=pendulum.datetime(2026, 10, 1, tz="Asia/Bangkok"),
    catchup=False,
    max_active_runs=1,
    params={
        "simulate_down": Param(
            "",
            type="string",
            enum=["", *SOURCES],
            description="จำลองว่าแหล่งข้อมูลนี้ล่ม (ทดสอบระดับ 3)",
        ),
        "xrates_days": Param(30, type="integer", minimum=1, maximum=90,
                             description="จำนวนวันย้อนหลังที่ scrape จาก x-rates.com"),
    },
    tags=["fx", "multi-source", "02739452"],
    doc_md=__doc__,
) as dag:

    create_tables = SQLExecuteQueryOperator(
        task_id="create_tables",
        conn_id=CONN_ID,
        sql=CREATE_TABLES_SQL,
    )

    # ===================== แหล่งที่ 1: Frankfurter API =====================
    @task_group(group_id="frankfurter")
    def frankfurter_group():
        @task
        def extract(**context) -> list[dict]:
            _check_simulated_outage("frankfurter", context)
            today = date.today()
            start = today.replace(year=today.year - HISTORY_YEARS)
            records = []
            # ขอทีละปี (ช่วงยาวมากๆ API อาจตอบช้า/ตัดข้อมูล)
            chunk_start = start
            while chunk_start <= today:
                chunk_end = min(chunk_start + timedelta(days=365), today)
                url = (f"https://api.frankfurter.dev/v1/{chunk_start}..{chunk_end}"
                       f"?base={BASE}&symbols={','.join(QUOTES)}")
                data = _http_get(url).json()
                for d, rates in data["rates"].items():
                    for q, v in rates.items():
                        records.append({"rate_date": d, "quote": q, "rate": v})
                chunk_start = chunk_end + timedelta(days=1)
            log.info("Frankfurter: %d records", len(records))
            return records

        @task
        def transform(records: list[dict]) -> list[dict]:
            return _normalize("frankfurter", records)

        @task
        def load_raw(rows: list[dict]) -> int:
            return _upsert_raw(rows)

        load_raw(transform(extract()))

    # ===================== แหล่งที่ 2: Yahoo Finance =====================
    @task_group(group_id="yahoo")
    def yahoo_group():
        @task
        def extract(**context) -> list[dict]:
            _check_simulated_outage("yahoo", context)
            now = datetime.now(timezone.utc)
            period1 = int((now - timedelta(days=365 * HISTORY_YEARS)).timestamp())
            period2 = int(now.timestamp())
            records = []
            for q in QUOTES:
                url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{BASE}{q}=X"
                       f"?period1={period1}&period2={period2}&interval=1d")
                result = _http_get(url).json()["chart"]["result"][0]
                closes = result["indicators"]["quote"][0]["close"]
                for ts, close in zip(result["timestamp"], closes):
                    if close is None:
                        continue
                    # ใช้วันที่แบบ UTC: ถ้าแปลงเป็นเวลาลอนดอน แท่งที่เปิดคืนวันอาทิตย์
                    # (23:00 UTC, สภาพคล่องต่ำ ราคาเพี้ยน) จะกลายเป็นวันจันทร์และต่างจาก
                    # แหล่งอื่นเกิน 3% -> ใช้ UTC แล้วตัดแท่งเสาร์-อาทิตย์ทิ้ง
                    d = datetime.fromtimestamp(ts, timezone.utc).date()
                    if d.weekday() >= 5:
                        continue
                    records.append({"rate_date": d.isoformat(), "quote": q, "rate": close})
                time.sleep(0.5)
            log.info("Yahoo: %d records", len(records))
            return records

        @task
        def transform(records: list[dict]) -> list[dict]:
            return _normalize("yahoo", records)

        @task
        def load_raw(rows: list[dict]) -> int:
            return _upsert_raw(rows)

        load_raw(transform(extract()))

    # ============ แหล่งที่ 3: x-rates.com (web scraping + Dynamic Task Mapping) ============
    @task_group(group_id="xrates")
    def xrates_group():
        @task
        def list_dates(**context) -> list[str]:
            _check_simulated_outage("xrates", context)
            days = int(context["params"].get("xrates_days") or 30)
            today = date.today()
            out = []
            for i in range(1, days + 1):  # เริ่มจากเมื่อวาน (วันนี้ตลาดยังไม่ปิด)
                d = today - timedelta(days=i)
                if d.weekday() < 5:
                    out.append(d.isoformat())
            return out

        @task(max_active_tis_per_dagrun=2)
        def scrape_day(day: str) -> list[dict]:
            from bs4 import BeautifulSoup

            url = f"https://www.x-rates.com/historical/?from={BASE}&amount=1&date={day}"
            try:
                html = _http_get(url).text
            except requests.RequestException as exc:
                # วันเดียวพังไม่ควรทำให้ทั้งแหล่งพัง -> ข้ามวันนั้นไป
                log.warning("ดึง %s ไม่สำเร็จ: %s", day, exc)
                return []
            finally:
                time.sleep(XRATES_DELAY_SEC)  # หน่วงทุก request ไม่ยิงถี่
            soup = BeautifulSoup(html, "html.parser")
            found = {}
            for table in soup.select("table.ratesTable"):
                for tr in table.select("tbody tr"):
                    a = tr.select_one("td.rtRates a")
                    if not a or "to=" not in a.get("href", ""):
                        continue
                    quote = a["href"].split("to=")[-1][:3].upper()
                    if quote in QUOTES and quote not in found:
                        found[quote] = a.get_text(strip=True).replace(",", "")
            if not found:
                log.warning("ไม่พบตารางเรตในหน้า %s (โครงสร้างหน้าเว็บอาจเปลี่ยน)", url)
            return [{"rate_date": day, "quote": q, "rate": v} for q, v in found.items()]

        @task
        def transform(pages) -> list[dict]:
            records = [r for page in pages for r in page]
            if not records:
                raise AirflowFailException("scrape x-rates.com ไม่ได้เลยสักวัน")
            return _normalize("xrates", records)

        @task
        def load_raw(rows: list[dict]) -> int:
            return _upsert_raw(rows)

        load_raw(transform(scrape_day.expand(day=list_dates())))

    groups = [frankfurter_group(), yahoo_group(), xrates_group()]

    # ===================== รวม + ตัดซ้ำข้ามแหล่ง =====================
    @task(trigger_rule=TriggerRule.ALL_DONE)
    def merge_dedup(**context) -> dict:
        dag_run = context["dag_run"]
        run_id = dag_run.run_id
        status = {}
        for src in SOURCES:
            ti = dag_run.get_task_instance(f"{src}.load_raw")
            ok = ti is not None and ti.state == "success"
            rows = ti.xcom_pull(task_ids=f"{src}.load_raw") if ok else 0
            status[src] = {"ok": ok, "rows": rows or 0}
        ok_sources = [s for s, v in status.items() if v["ok"]]
        log.info("สถานะแหล่งข้อมูล: %s", status)

        hook = PostgresHook(postgres_conn_id=CONN_ID)
        for src, v in status.items():
            hook.run(
                """INSERT INTO source_runs (run_id, source, status, rows) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (run_id, source) DO UPDATE
                   SET status = EXCLUDED.status, rows = EXCLUDED.rows""",
                parameters=(run_id, src, "success" if v["ok"] else "failed", v["rows"]),
            )
        if not ok_sources:
            raise AirflowFailException("ทุกแหล่งล่ม ไม่มีข้อมูลให้รวม")

        # ตัดซ้ำข้ามแหล่ง: วัน+สกุลเดียวกันจากหลายแหล่ง -> เหลือ 1 แถว (ใช้ค่ามัธยฐาน)
        hook.run(
            """
            INSERT INTO fx_rates (rate_date, base, quote, rate, rate_min, rate_max,
                                  spread_pct, source_count, sources, updated_at)
            SELECT rate_date, base, quote,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rate),
                   MIN(rate), MAX(rate),
                   (MAX(rate) - MIN(rate))
                       / PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rate) * 100,
                   COUNT(DISTINCT source),
                   STRING_AGG(source, ',' ORDER BY source),
                   NOW()
            FROM fx_rates_raw
            GROUP BY rate_date, base, quote
            ON CONFLICT (rate_date, base, quote) DO UPDATE SET
                rate = EXCLUDED.rate, rate_min = EXCLUDED.rate_min,
                rate_max = EXCLUDED.rate_max, spread_pct = EXCLUDED.spread_pct,
                source_count = EXCLUDED.source_count, sources = EXCLUDED.sources,
                updated_at = NOW();
            """
        )
        raw_rows = hook.get_first("SELECT COUNT(*) FROM fx_rates_raw")[0]
        unified_rows = hook.get_first("SELECT COUNT(*) FROM fx_rates")[0]
        log.info("raw %d แถว -> รวมแล้ว %d แถว (ตัดซ้ำข้ามแหล่งออก %d แถว)",
                 raw_rows, unified_rows, raw_rows - unified_rows)
        return {
            "sources_ok": ok_sources,
            "sources_failed": [s for s in SOURCES if s not in ok_sources],
            "raw_rows": raw_rows,
            "unified_rows": unified_rows,
        }

    # ===================== ตรวจคุณภาพ + แตกเส้นทาง =====================
    @task.branch
    def quality_check(merge_info: dict, **context) -> str:
        run_id = context["dag_run"].run_id
        hook = PostgresHook(postgres_conn_id=CONN_ID)
        total, bad_rate, latest, n_quotes, bad_spread = hook.get_first(
            f"""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE rate IS NULL OR rate <= 0),
                   MAX(rate_date),
                   COUNT(DISTINCT quote) FILTER (WHERE rate_date >= CURRENT_DATE - 7),
                   COUNT(*) FILTER (WHERE spread_pct > {DQ_MAX_SPREAD_PCT})
            FROM fx_rates
            """
        )
        stale_days = (date.today() - latest).days if latest else 999
        bad_share = (bad_spread / total * 100) if total else 100.0
        checks = [
            ("min_rows", total >= DQ_MIN_ROWS, f"{total} แถว (ต้อง >= {DQ_MIN_ROWS})"),
            ("valid_rate", bad_rate == 0, f"เรต <= 0 หรือว่าง {bad_rate} แถว"),
            ("all_quotes", n_quotes == len(QUOTES),
             f"มี {n_quotes}/{len(QUOTES)} สกุลในช่วง 7 วันล่าสุด"),
            ("freshness", stale_days <= DQ_MAX_STALE_DAYS,
             f"ข้อมูลล่าสุด {latest} (ห่าง {stale_days} วัน, ยอมได้ {DQ_MAX_STALE_DAYS})"),
            ("cross_source_agree", bad_share <= DQ_MAX_BAD_SPREAD_SHARE,
             f"{bad_spread} แถว ({bad_share:.2f}%) ต่างกันเกิน {DQ_MAX_SPREAD_PCT}% "
             f"(ยอมได้ {DQ_MAX_BAD_SPREAD_SHARE}%)"),
        ]
        for name, passed, detail in checks:
            log.info("[%s] %s — %s", "PASS" if passed else "FAIL", name, detail)
            hook.run(
                """INSERT INTO dq_results (run_id, check_name, passed, detail)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (run_id, check_name) DO UPDATE
                   SET passed = EXCLUDED.passed, detail = EXCLUDED.detail, checked_at = NOW()""",
                parameters=(run_id, name, passed, detail),
            )
        all_passed = all(p for _, p, _ in checks)
        return "publish" if all_passed else "quarantine"

    @task
    def publish() -> int:
        """ผ่าน -> แทนที่ตารางที่ dashboard อ่านทั้งก้อนใน transaction เดียว"""
        hook = PostgresHook(postgres_conn_id=CONN_ID)
        hook.run(
            ["DELETE FROM fx_rates_published",
             "INSERT INTO fx_rates_published SELECT * FROM fx_rates"],
            autocommit=False,
        )
        n = hook.get_first("SELECT COUNT(*) FROM fx_rates_published")[0]
        log.info("publish %d แถวขึ้น dashboard", n)
        return n

    @task
    def quarantine(**context) -> int:
        """ไม่ผ่าน -> ไม่แตะตาราง dashboard (ยังเห็นข้อมูลชุดดีล่าสุด) และเก็บแถวที่มีปัญหาไว้"""
        run_id = context["dag_run"].run_id
        hook = PostgresHook(postgres_conn_id=CONN_ID)
        hook.run(
            f"""
            INSERT INTO fx_rates_quarantine (run_id, rate_date, quote, rate, spread_pct, sources, reason)
            SELECT %s, rate_date, quote, rate, spread_pct, sources,
                   CASE WHEN rate IS NULL OR rate <= 0 THEN 'invalid rate'
                        ELSE 'sources disagree > {DQ_MAX_SPREAD_PCT}%%' END
            FROM fx_rates
            WHERE rate IS NULL OR rate <= 0 OR spread_pct > {DQ_MAX_SPREAD_PCT}
            ON CONFLICT DO NOTHING
            """,
            parameters=(run_id,),
        )
        n = hook.get_first(
            "SELECT COUNT(*) FROM fx_rates_quarantine WHERE run_id = %s", parameters=(run_id,)
        )[0]
        log.warning("quality check ไม่ผ่าน: กักแถวที่มีปัญหาไว้ %d แถว, dashboard ไม่ถูกอัปเดต", n)
        return n

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def record_run(**context):
        dag_run = context["dag_run"]
        ti = context["ti"]
        info = ti.xcom_pull(task_ids="merge_dedup") or {}
        published = dag_run.get_task_instance("publish")
        quarantined = dag_run.get_task_instance("quarantine")
        branch = ("publish" if published and published.state == "success"
                  else "quarantine" if quarantined and quarantined.state == "success"
                  else None)
        failed = info.get("sources_failed", SOURCES)
        if not info:
            status = "FAILED"
        elif branch == "quarantine":
            status = "DQ_FAILED"
        elif branch == "publish":
            status = "PARTIAL" if failed else "SUCCESS"
        else:
            status = "FAILED"
        hook = PostgresHook(postgres_conn_id=CONN_ID)
        hook.run(
            """
            INSERT INTO pipeline_runs (run_id, started_at, finished_at, status, sources_ok,
                                       sources_failed, raw_rows, unified_rows, dq_passed, branch)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                finished_at = NOW(), status = EXCLUDED.status, sources_ok = EXCLUDED.sources_ok,
                sources_failed = EXCLUDED.sources_failed, raw_rows = EXCLUDED.raw_rows,
                unified_rows = EXCLUDED.unified_rows, dq_passed = EXCLUDED.dq_passed,
                branch = EXCLUDED.branch
            """,
            parameters=(
                dag_run.run_id, dag_run.start_date, status,
                ",".join(info.get("sources_ok", [])), ",".join(failed),
                info.get("raw_rows"), info.get("unified_rows"),
                branch == "publish" if branch else None, branch,
            ),
        )
        log.info("รอบนี้: %s (branch=%s, แหล่งที่ล่ม=%s)", status, branch, failed)

    merged = merge_dedup()
    branch = quality_check(merged)
    publish_task = publish()
    quarantine_task = quarantine()
    done = record_run()
    end = EmptyOperator(task_id="end", trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)

    create_tables >> groups >> merged
    branch >> [publish_task, quarantine_task] >> done >> end
