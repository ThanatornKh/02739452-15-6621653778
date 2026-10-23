# 02739452-15-6621653778 — FX Multi-Source Pipeline

ระบบรวบรวม **อัตราแลกเปลี่ยนเงินบาท (THB) เทียบเยน (JPY) ดอลลาร์สหรัฐ (USD) ยูโร (EUR) และวอน (KRW)**
จาก 3 แหล่ง มารวมเป็นชุดข้อมูลเดียวด้วย Apache Airflow แล้วเก็บใน PostgreSQL และแสดงผลบน
dashboard ที่พัฒนาเองด้วย Streamlit (อ่านจาก PostgreSQL โดยตรง)

ข้อสอบปลายภาค วิชา 02739452 แพลตฟอร์มข้อมูลขนาดใหญ่และการวิเคราะห์ ภาคต้น ปีการศึกษา 2569
(ลำดับที่ 15, รหัสนิสิต 6621653778)

## หัวข้อ

| | |
|---|---|
| หมวด | อัตราแลกเปลี่ยนเงินตรา |
| ขอบเขต | ค่าเงินบาทเทียบ JPY / USD / EUR / KRW รายวัน ย้อนหลัง 6 ปี |
| ผลลัพธ์ | ~6,200 แถวหลังรวมและตัดซ้ำ (ข้อมูลดิบ ~12,500 แถวจาก 3 แหล่ง) |

## แหล่งข้อมูล

| # | แหล่ง | วิธีดึง | ช่วงข้อมูล |
|---|---|---|---|
| 1 | [Frankfurter API](https://frankfurter.dev) (ข้อมูลอ้างอิงของธนาคารกลางยุโรป ECB) | REST API (JSON) ขอทีละปี | 6 ปี |
| 2 | [Yahoo Finance](https://finance.yahoo.com) chart endpoint (`THBJPY=X` ฯลฯ) | HTTP (JSON) | 6 ปี |
| 3 | [x-rates.com](https://www.x-rates.com/historical/?from=THB) หน้า Historical Rates | **Web scraping** ด้วย `requests` + `BeautifulSoup` (ไม่ใช้ Selenium) | 30 วันล่าสุด (ปรับได้) |

**จริยธรรมและกฎหมาย**
- `robots.txt` ของ x-rates.com อนุญาตทุก path ยกเว้น `/auth/` และระบบดึงเฉพาะหน้า `/historical/`
- scrape ทีละวันแบบหน่วงเวลา 1 วินาทีต่อ request และให้ทำงานพร้อมกันได้ไม่เกิน 2 task พร้อมประกาศ User-Agent ของโปรเจกต์
- ข้อมูลทั้งหมดเป็นอัตราแลกเปลี่ยน **ไม่มีข้อมูลส่วนบุคคล** (สอดคล้อง PDPA)

## สถาปัตยกรรม

```
                ┌─ TaskGroup frankfurter: extract → transform → load_raw ─┐
create_tables ──┼─ TaskGroup yahoo:       extract → transform → load_raw ─┼─> merge_dedup ─> quality_check ─┬─> publish ────┐
                └─ TaskGroup xrates: list_dates → scrape_day[] → transform → load_raw ┘   (all_done)  (branch)    └─> quarantine ─┴─> record_run ─> end
                                     (Dynamic Task Mapping)
```

| ตาราง | หน้าที่ |
|---|---|
| `fx_rates_raw` | ข้อมูลดิบทุกแหล่งใน schema เดียวกัน, PK `(source, rate_date, base, quote)` + `INSERT … ON CONFLICT DO UPDATE` |
| `fx_rates` | รวมทุกแหล่งและตัดรายการซ้ำข้ามแหล่ง: 1 แถวต่อ (วัน, สกุล), ใช้ค่ามัธยฐาน, เก็บ `spread_pct` และ `source_count` |
| `fx_rates_published` | ตารางที่ dashboard อ่าน อัปเดตเฉพาะรอบที่ผ่าน quality check |
| `fx_rates_quarantine` | แถวที่ไม่ผ่าน quality check |
| `pipeline_runs`, `source_runs`, `dq_results` | สถานะแต่ละรอบ แต่ละแหล่ง และผลตรวจคุณภาพ (หน้า Pipeline Status ใช้ข้อมูลจากตารางเหล่านี้) |

### ฟีเจอร์ตามระดับของโจทย์
- **ระดับ 1:** มี DAG แบบ extract → transform → load ลง PostgreSQL และเว็บแสดงตารางกับกราฟ
- **ระดับ 2:** แต่ละแหล่งอยู่ใน TaskGroup ของตัวเองและรันขนานกัน ข้อมูลทุกแหล่งรวมอยู่ใน schema เดียว ใช้ UPSERT จึงรันซ้ำแล้วจำนวนแถวไม่เพิ่ม เว็บมี KPI และตัวกรอง (สกุล / ช่วงเวลา / จำนวนแหล่งที่ยืนยัน)
- **ระดับ 3:**
  - ดึงข้อมูล 3 แหล่ง
  - `merge_dedup` ตั้ง `trigger_rule=all_done` ถ้าแหล่งไหนล่มก็ยังรวมข้อมูลจากแหล่งที่เหลือได้
  - ตัดรายการซ้ำข้ามแหล่งด้วย `GROUP BY (rate_date, quote)`
  - `quality_check` เป็น `@task.branch` ตรวจ 5 ข้อ ได้แก่ จำนวนแถว, เรตที่ใช้ไม่ได้, มีครบทุกสกุล, ความสดของข้อมูล และความต่างระหว่างแหล่ง ถ้าผ่านไป `publish` ถ้าไม่ผ่านไป `quarantine`
- **โบนัส:** มีหน้า Pipeline Status บนเว็บ และใช้ Dynamic Task Mapping (`scrape_day.expand`)

## วิธีรัน

ต้องมี Docker Desktop (แนะนำ RAM อย่างน้อย 4 GB) และพอร์ต 8090, 8501, 5435 ต้องว่าง

```bash
git clone https://github.com/ThanatornKh/02739452-15-6621653778.git
cd 02739452-15-6621653778
cp .env.example .env          # แล้วแก้รหัสผ่านใน .env ได้ตามต้องการ
docker compose up -d --build  # ครั้งแรกใช้เวลา build ประมาณ 2-4 นาที
```

| บริการ | URL | หมายเหตุ |
|---|---|---|
| Dashboard | http://localhost:8501 | หน้า Pipeline Status อยู่ในเมนูด้านซ้าย |
| Airflow UI | http://localhost:8090 | user/pass ตาม `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` ใน `.env` |
| PostgreSQL | `localhost:5435` | db/user/pass ตาม `TARGET_DB_*` ใน `.env` |

- DAG `fx_multi_source_dag` **เปิดใช้งานอัตโนมัติและรันรอบแรกเองทันที** ใช้เวลาประมาณ 1 นาที เสร็จแล้วรีเฟรช dashboard ได้เลย หลังจากนั้นรันทุกวันเวลา 07:00 น.
- **ทดสอบกรณีแหล่งข้อมูลล่ม:** ใน Airflow UI กด ▶ Trigger DAG w/ config แล้วเลือก `simulate_down = yahoo` (หรือ `frankfurter` / `xrates`) DAG ยังรวมข้อมูลจากแหล่งที่เหลือได้ และหน้า Pipeline Status จะขึ้นสถานะ 🟡 PARTIAL
- **ทดสอบ UPSERT:** Trigger ซ้ำกี่รอบ จำนวนแถวใน `fx_rates_raw` / `fx_rates` ก็ไม่เพิ่ม

```sql
-- ตรวจข้อมูลด้วย psql / DBeaver
SELECT source, COUNT(*) FROM fx_rates_raw GROUP BY source;
SELECT COUNT(*) FROM fx_rates;
SELECT * FROM pipeline_runs ORDER BY finished_at DESC;
```

หยุดระบบด้วย `docker compose down` และถ้าต้องการล้างข้อมูลทั้งหมดใช้ `docker compose down -v`

## โครงสร้างไฟล์

```
dags/fx_multi_source_dag.py   DAG หลัก (3 แหล่ง, TaskGroup, UPSERT, dedup, branch, mapping)
web/Dashboard.py              Dashboard: KPI, ตัวกรอง, กราฟ, ตาราง
web/pages/1_Pipeline_Status.py หน้าสถานะ pipeline
web/db.py                     เชื่อม PostgreSQL ตรงด้วย psycopg2
docker-compose.yml            Airflow (LocalExecutor) + PostgreSQL x2 + web
Dockerfile, requirements.txt  image ของ Airflow + แพ็กเกจที่ DAG ใช้
.env.example                  ตัวอย่างค่าตั้ง (ไฟล์ .env จริงไม่ถูก commit)
docs/                         ภาพหน้าจอและไฟล์สรุป
```
