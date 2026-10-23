"""ธีมของ dashboard — โทนดำ/ขาวแบบมินิมอล ได้แรงบันดาลใจจาก koenigsegg.com
(พื้นดำสนิท, ตัวอักษร grotesk, หัวข้อตัวพิมพ์ใหญ่เว้นช่องไฟกว้าง, เส้นแบ่งบางๆ, จุดเน้นสีแดง)"""

import html

import streamlit as st

ACCENT = "#d0021b"
STATUS_COLOR = {
    "SUCCESS": "#2ecc71", "PASS": "#2ecc71", "success": "#2ecc71",
    "PARTIAL": "#f5c518",
    "DQ_FAILED": "#ff8c1a",
    "FAILED": "#ff3b30", "FAIL": "#ff3b30", "failed": "#ff3b30",
}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@300;400;500;600&family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"], .stApp, .stMarkdown, p, label, input, textarea, button,
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] {{
    font-family: 'Inter', 'IBM Plex Sans Thai', sans-serif !important;
}}
.stApp {{ background: #000; }}
[data-testid="stDecoration"], [data-testid="stToolbar"] {{ display: none; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.5rem; max-width: 1280px; }}

/* sidebar */
[data-testid="stSidebar"] {{ background: #070707; border-right: 1px solid #1c1c1c; }}
[data-testid="stSidebarNav"] a span {{
    text-transform: uppercase; letter-spacing: .14em; font-size: .78rem; color: #bdbdbd;
}}
[data-testid="stSidebar"] h2 {{
    text-transform: uppercase; letter-spacing: .2em; font-size: .75rem; color: #8a8a8a;
    font-weight: 500;
}}

/* hero */
.kx-hero {{ padding: 1.2rem 0 2.2rem; border-bottom: 1px solid #1c1c1c; margin-bottom: 2rem; }}
.kx-eyebrow {{
    text-transform: uppercase; letter-spacing: .32em; font-size: .72rem; color: #8a8a8a;
}}
.kx-title {{
    font-size: 3.1rem; line-height: 1.05; font-weight: 700; color: #fff; margin: .6rem 0 .8rem;
    letter-spacing: -.01em; text-transform: uppercase;
}}
.kx-title em {{ font-style: normal; color: {ACCENT}; }}
.kx-sub {{ color: #9b9b9b; font-size: .95rem; max-width: 760px; font-weight: 300; }}
.kx-line {{
    height: 2px; width: 120px; margin-top: 1.4rem;
    background: linear-gradient(90deg, {ACCENT}, rgba(208,2,27,0));
    box-shadow: 0 0 14px rgba(208,2,27,.65);
}}

/* section headings */
.kx-section {{
    display: flex; align-items: baseline; gap: 1rem; margin: 2.6rem 0 1.1rem;
    border-top: 1px solid #1c1c1c; padding-top: 1.1rem;
}}
.kx-section .num {{ color: {ACCENT}; font-size: .75rem; letter-spacing: .2em; }}
.kx-section .name {{
    text-transform: uppercase; letter-spacing: .26em; font-size: .85rem; color: #fff;
    font-weight: 500;
}}
.kx-section .note {{ margin-left: auto; color: #6f6f6f; font-size: .8rem; }}

/* metrics: ไม่มีกรอบ มีแค่เส้นบางด้านบน */
[data-testid="stMetric"] {{ border-top: 1px solid #262626; padding-top: .8rem; }}
[data-testid="stMetricLabel"] p {{
    text-transform: uppercase; letter-spacing: .16em; font-size: .7rem !important; color: #8a8a8a;
}}
[data-testid="stMetricValue"] {{ font-weight: 300; font-size: 2.2rem; color: #fff; }}

/* status */
.kx-status {{ display: inline-flex; align-items: center; gap: .55rem;
    text-transform: uppercase; letter-spacing: .18em; font-size: .8rem; color: #fff; }}
.kx-dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
.kx-kv {{ border-top: 1px solid #262626; padding-top: .8rem; }}
.kx-kv .k {{ text-transform: uppercase; letter-spacing: .16em; font-size: .7rem; color: #8a8a8a; }}
.kx-kv .v {{ font-size: 1.25rem; font-weight: 300; color: #fff; margin-top: .35rem; }}

.stCaption, [data-testid="stCaptionContainer"] {{ color: #6f6f6f !important; }}
.stDownloadButton button {{
    background: transparent; border: 1px solid #3a3a3a; color: #fff; border-radius: 0;
    text-transform: uppercase; letter-spacing: .2em; font-size: .72rem; padding: .6rem 1.4rem;
}}
.stDownloadButton button:hover {{ border-color: #fff; color: #fff; }}
</style>
"""


def apply_style() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(eyebrow: str, title_html: str, sub: str) -> None:
    st.markdown(
        f'<div class="kx-hero"><div class="kx-eyebrow">{html.escape(eyebrow)}</div>'
        f'<div class="kx-title">{title_html}</div>'
        f'<div class="kx-sub">{html.escape(sub)}</div><div class="kx-line"></div></div>',
        unsafe_allow_html=True,
    )


def section(num: str, name: str, note: str = "") -> None:
    st.markdown(
        f'<div class="kx-section"><span class="num">{num}</span>'
        f'<span class="name">{html.escape(name)}</span>'
        f'<span class="note">{html.escape(note)}</span></div>',
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    color = STATUS_COLOR.get(status, "#8a8a8a")
    return (f'<span class="kx-status"><span class="kx-dot" style="background:{color};'
            f'box-shadow:0 0 10px {color}"></span>{html.escape(status)}</span>')


def kv(label: str, value_html: str) -> str:
    return f'<div class="kx-kv"><div class="k">{html.escape(label)}</div><div class="v">{value_html}</div></div>'


def color_status(value) -> str:
    """ใช้กับ pandas Styler: ระบายสีตัวอักษรตามสถานะ"""
    for key, color in STATUS_COLOR.items():
        if isinstance(value, str) and key in value:
            return f"color: {color}; font-weight: 500"
    return ""
