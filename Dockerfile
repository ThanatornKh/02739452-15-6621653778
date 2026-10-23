# image ของ Airflow + แพ็กเกจที่ DAG ต้องใช้ (ติดตั้งตอน build ครั้งเดียว
# ไม่ใช้ _PIP_ADDITIONAL_REQUIREMENTS เพราะจะ pip install ใหม่ทุกครั้งที่ container เริ่ม)
FROM apache/airflow:2.10.4-python3.11

COPY requirements.txt /requirements.txt
# ใส่ apache-airflow==2.10.4 ไว้ด้วย กัน pip เผลออัปเกรด/ดาวน์เกรด Airflow เอง
RUN pip install --no-cache-dir "apache-airflow==2.10.4" -r /requirements.txt
