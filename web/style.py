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

_CSS_TEMPLATE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@300;400;500;600&family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"], .stApp, .stMarkdown, p, label, input, textarea, button,
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] {{
    font-family: 'Inter', 'IBM Plex Sans Thai', sans-serif !important;
}}
.stApp {{ background: {bg}; }}
[data-testid="stDecoration"], [data-testid="stToolbar"] {{ display: none; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.5rem; max-width: 1280px; }}
/* สวิตช์ธีมมุมขวาบน */
[data-testid="stHorizontalBlock"]:has(#kx-theme-anchor) {{ margin-bottom: -1.6rem; }}
[data-testid="stColumn"]:has(#kx-theme-anchor) [data-testid="stVerticalBlock"] {{
    align-items: flex-end; gap: 0;
}}
[data-testid="stColumn"]:has(#kx-theme-anchor) [data-testid="stElementContainer"]:has(#kx-theme-anchor) {{
    display: none;
}}
[data-testid="stColumn"]:has(#kx-theme-anchor) label p {{
    text-transform: uppercase; letter-spacing: .16em; font-size: .72rem !important;
    white-space: nowrap;
}}

/* sidebar */
[data-testid="stSidebar"] {{ background: {panel}; border-right: 1px solid {line}; }}
[data-testid="stSidebarNav"] a span {{
    text-transform: uppercase; letter-spacing: .14em; font-size: .78rem; color: {nav};
}}
[data-testid="stSidebar"] h2 {{
    text-transform: uppercase; letter-spacing: .2em; font-size: .75rem; color: {muted};
    font-weight: 500;
}}

/* hero */
.kx-hero {{ padding: 1.2rem 0 2.2rem; border-bottom: 1px solid {line}; margin-bottom: 2rem; }}
.kx-eyebrow {{
    text-transform: uppercase; letter-spacing: .32em; font-size: .72rem; color: {muted};
}}
.kx-title {{
    font-size: 3.1rem; line-height: 1.05; font-weight: 700; color: {text}; margin: .6rem 0 .8rem;
    letter-spacing: -.01em; text-transform: uppercase;
}}
.kx-title em {{ font-style: normal; color: {accent}; }}
.kx-sub {{ color: {sub}; font-size: .95rem; max-width: 760px; font-weight: 300; }}
.kx-line {{
    height: 2px; width: 120px; margin-top: 1.4rem;
    background: linear-gradient(90deg, {accent}, rgba(208,2,27,0));
    box-shadow: 0 0 14px rgba(208,2,27,.65);
}}

/* section headings */
.kx-section {{
    display: flex; align-items: baseline; gap: 1rem; margin: 2.6rem 0 1.1rem;
    border-top: 1px solid {line}; padding-top: 1.1rem;
}}
.kx-section .num {{ color: {accent}; font-size: .75rem; letter-spacing: .2em; }}
.kx-section .name {{
    text-transform: uppercase; letter-spacing: .26em; font-size: .85rem; color: {text};
    font-weight: 500;
}}
.kx-section .note {{ margin-left: auto; color: {faint}; font-size: .8rem; }}

/* metrics: ไม่มีกรอบ มีแค่เส้นบางด้านบน */
[data-testid="stMetric"] {{ border-top: 1px solid {line2}; padding-top: .8rem; }}
[data-testid="stMetricLabel"] p {{
    text-transform: uppercase; letter-spacing: .16em; font-size: .7rem !important; color: {muted};
}}
[data-testid="stMetricValue"] {{ font-weight: 300; font-size: 2.2rem; color: {text}; }}

/* sidebar: เส้นแบ่งหัวข้อชัดเจน */
[data-testid="stSidebar"] h2 {{
    border-bottom: 1px solid {accent}; padding-bottom: .55rem !important; margin: 1.6rem 0 .2rem !important;
    color: {text} !important; letter-spacing: .28em; font-size: .78rem; font-weight: 600;
}}
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stWidgetLabel"]) {{
    border-top: 1px solid {line2}; padding-top: .85rem; margin-top: .35rem;
}}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{ font-weight: 600; font-size: .9rem; }}
[data-testid="stSidebarNav"] {{ border-bottom: 1px solid {line2}; padding-bottom: .8rem; }}

/* แท็กที่เลือกใน multiselect ของ sidebar: เต็มแถว กว้างเท่ากัน เรียงเป็นรายการ */
[data-testid="stSidebar"] [data-baseweb="tag"] {{
    width: 100%; max-width: none; margin: 3px 0; height: 30px; border-radius: 2px;
    justify-content: space-between; padding: 0 8px 0 12px;
}}
[data-testid="stSidebar"] [data-baseweb="tag"] > span:first-child {{
    max-width: none; overflow: visible; letter-spacing: .04em;
}}

/* status */
.kx-status {{ display: inline-flex; align-items: center; gap: .55rem;
    text-transform: uppercase; letter-spacing: .18em; font-size: .8rem; color: {text}; }}
.kx-dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
.kx-kv {{ border-top: 1px solid {line2}; padding-top: .8rem; }}
.kx-kv .k {{ text-transform: uppercase; letter-spacing: .16em; font-size: .7rem; color: {muted}; }}
.kx-kv .v {{ font-size: 1.25rem; font-weight: 300; color: {text}; margin-top: .35rem; }}

.stCaption, [data-testid="stCaptionContainer"] {{ color: {faint} !important; }}
.stDownloadButton button {{
    background: transparent; border: 1px solid {line3}; color: {text}; border-radius: 0;
    text-transform: uppercase; letter-spacing: .2em; font-size: .72rem; padding: .6rem 1.4rem;
}}
.stDownloadButton button:hover {{ border-color: {text}; color: {text}; }}
</style>
"""


PALETTES = {
    "dark": dict(bg="#000000", panel="#070707", line="#1c1c1c", line2="#262626", line3="#3a3a3a",
                 text="#ffffff", sub="#9b9b9b", muted="#8a8a8a", faint="#6f6f6f", nav="#bdbdbd",
                 accent=ACCENT),
    "light": dict(bg="#ffffff", panel="#f6f6f6", line="#e6e6e6", line2="#e0e0e0", line3="#bdbdbd",
                  text="#0a0a0a", sub="#555555", muted="#6b6b6b", faint="#8a8a8a", nav="#333333",
                  accent=ACCENT),
}
# ธีมขาว: ธีมของ Streamlit เองเป็นโทนดำ (config.toml) จึงต้องบังคับสีของ widget ด้วย CSS
# ไม่สลับธีมฝั่ง server เพราะค่านั้นใช้ร่วมกันทุกหน้าต่าง และเบราว์เซอร์จำธีมเดิมไว้
_LIGHT_EXTRA = """
<style>
.stApp, [data-testid="stSidebar"] {{ color: {text}; }}
.stApp p, .stApp label, .stApp span, .stApp li, .stApp small,
[data-testid="stWidgetLabel"] *, [data-testid="stMarkdownContainer"] *,
[data-testid="stTickBarMin"], [data-testid="stTickBarMax"],
[data-testid="stThumbValue"], [data-testid="stSidebarCollapseButton"] * {{ color: {text}; }}
[data-testid="stCaptionContainer"] *, .kx-section .note, .kx-sub {{ color: {sub} !important; }}
[data-testid="stMetricDelta"] * {{ color: inherit; }}
[data-testid="stMetricDelta"] {{ color: {accent} !important; }}
.kx-eyebrow, .kx-kv .k, [data-testid="stMetricLabel"] p, [data-testid="stSidebar"] h2 {{ color: {muted} !important; }}
.kx-section .num, .kx-title em {{ color: {accent} !important; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {{ color: {text} !important; }}
/* ช่องเลือก */
[data-baseweb="select"] > div {{ background: #f3f3f3 !important; border-color: #dcdcdc !important; color: {text} !important; }}
[data-baseweb="select"] input, [data-baseweb="select"] svg {{ color: {text} !important; fill: {text} !important; }}
[data-baseweb="tag"] span, [data-baseweb="tag"] svg {{ color: #fff !important; fill: #fff !important; }}
[data-baseweb="popover"] ul, [data-baseweb="popover"] li {{ background: #fff !important; color: {text} !important; }}
[data-baseweb="popover"] li:hover {{ background: #f0f0f0 !important; }}
[data-baseweb="input"] > div, [data-baseweb="input"] input {{ background: #f3f3f3 !important; color: {text} !important; }}
/* radio: วงกลมที่ยังไม่เลือกเป็นขาวมีขอบ */
[data-baseweb="radio"] > div:first-child {{ background: #fff !important; box-shadow: inset 0 0 0 1px #9a9a9a; }}
[data-baseweb="radio"] > div:first-child > div {{ background: #fff !important; }}
[data-baseweb="radio"]:has(input:checked) > div:first-child {{ background: {accent} !important; box-shadow: none; }}
/* toggle ที่ปิดอยู่ */
[data-baseweb="checkbox"] > div:first-child {{ background: #cfcfcf; }}
[data-baseweb="checkbox"]:has(input:checked) > div:first-child {{ background: {accent}; }}
/* ตาราง (วาดบน canvas ด้วยธีมดำ) -> กลับสีเป็นขาว โดยคงเฉดสีสถานะไว้ */
[data-testid="stDataFrame"] {{ filter: invert(1) hue-rotate(180deg); }}
[data-testid="stAlert"] * {{ color: {text} !important; }}
</style>
"""


def theme_mode() -> str:
    return st.session_state.get("kx_mode", "dark")


def theme_toggle() -> str:
    """สวิตช์ธีมขาว/ดำที่มุมขวาบนของหน้า — เก็บโหมดใน session_state คีย์ธรรมดา (ไม่ใช่คีย์ของ widget)
    เพราะ Streamlit ล้างค่า widget ทิ้งเมื่อเปลี่ยนหน้า ธีมจะได้คงเดิมทุกหน้า"""
    st.session_state.setdefault("kx_mode", "dark")

    def _flip():
        st.session_state["kx_mode"] = "light" if st.session_state["_kx_light"] else "dark"

    _, right = st.columns([5, 1])
    with right:
        # anchor ให้ CSS หาคอลัมน์นี้เจอ แล้วชิดขวา
        st.markdown('<span id="kx-theme-anchor"></span>', unsafe_allow_html=True)
        st.toggle("Light theme", value=st.session_state["kx_mode"] == "light",
                  key="_kx_light", on_change=_flip)
    return st.session_state["kx_mode"]


def style_chart(chart):
    """แกน/ตัวอักษร/พื้นหลังของกราฟตามธีม — สีเส้นกำหนดไว้ที่ตัวกราฟเอง จึงเหมือนเดิมทั้งสองธีม"""
    p = PALETTES[theme_mode()]
    grid = "#262626" if theme_mode() == "dark" else "#e6e6e6"
    return (
        chart.configure(background=p["bg"], font="Inter, IBM Plex Sans Thai, sans-serif")
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=p["sub"], titleColor=p["sub"], gridColor=grid,
                        domainColor=grid, tickColor=grid, labelFontSize=12, titleFontSize=12,
                        titlePadding=12, labelPadding=6)
        .configure_axisX(grid=False)
        .configure_legend(labelColor=p["text"], titleColor=p["sub"], labelFontSize=13,
                          titleFontSize=13, symbolStrokeWidth=3)
    )


def apply_style() -> None:
    mode = theme_toggle()
    st.markdown(_CSS_TEMPLATE.format(**PALETTES[mode]), unsafe_allow_html=True)
    if mode == "light":
        st.markdown(_LIGHT_EXTRA.format(**PALETTES["light"]), unsafe_allow_html=True)


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
