"""การเชื่อมต่อ PostgreSQL ที่ทุกหน้าใช้ร่วมกัน (อ่านตรงจากฐานข้อมูล ไม่ผ่าน API)"""

import os
import warnings

import pandas as pd
import psycopg2
import streamlit as st

# pandas เตือนเมื่อใช้ connection ของ psycopg2 ตรงๆ แทน SQLAlchemy — ใช้งานได้ปกติ
warnings.filterwarnings("ignore", message=".*pandas only supports SQLAlchemy.*")

QUOTE_INFO = {
    "JPY": {"name": "เยนญี่ปุ่น", "unit": 100},
    "USD": {"name": "ดอลลาร์สหรัฐ", "unit": 1},
    "EUR": {"name": "ยูโร", "unit": 1},
    "KRW": {"name": "วอนเกาหลีใต้", "unit": 1000},
}


def _connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5435")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
    )


@st.cache_data(ttl=30, show_spinner=False)
def query(sql: str, params: tuple | None = None) -> pd.DataFrame:
    """คืน DataFrame ว่างถ้าตารางยังไม่ถูกสร้าง (DAG ยังไม่เคยรัน)"""
    try:
        with _connect() as conn:
            return pd.read_sql(sql, conn, params=params)
    except (psycopg2.errors.UndefinedTable, psycopg2.OperationalError) as exc:
        st.session_state["db_error"] = str(exc).splitlines()[0]
        return pd.DataFrame()


def thb_per_unit(df: pd.DataFrame, col: str = "rate") -> pd.Series:
    """เรตในฐานข้อมูลคือ 1 THB = x สกุล -> แปลงเป็น 'N หน่วย = กี่บาท' ที่คนไทยคุ้นตา"""
    units = df["quote"].map(lambda q: QUOTE_INFO[q]["unit"])
    return units / df[col]


def unit_label(quote: str) -> str:
    info = QUOTE_INFO[quote]
    return f"{info['unit']:,} {quote}"
