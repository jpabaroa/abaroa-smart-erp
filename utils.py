"""
utils.py — Abaroa Smart ERP
Tema premium: Outfit font, glassmorphism refinado, formularios profesionales, mobile responsive.
"""

from pathlib import Path
from io import BytesIO

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

BASE_DIR = Path(__file__).resolve().parent

# ── Logos ─────────────────────────────────────────────────────────────────────
def _first_existing(*paths):
    for p in paths:
        if Path(p).exists():
            return Path(p)
    return paths[0]

LOGO_CROP_PATH = _first_existing(BASE_DIR / "logo-abaroasmart-crop.png", BASE_DIR / "logo-abaroasmart.png")
LOGO_PATH      = _first_existing(BASE_DIR / "logo-abaroasmart.svg", BASE_DIR / "logo-azul-abaroasmart.svg")

def _pdf_logo_path():
    for path in [LOGO_CROP_PATH, BASE_DIR / "logo-abaroasmart.png"]:
        if Path(path).exists():
            return path
    return None

# ── Formato ───────────────────────────────────────────────────────────────────
def money(x):
    try:
        return "$ " + format(int(round(float(x))), ",").replace(",", ".")
    except Exception:
        return "$ 0"

def logo(width=200):
    for path in [LOGO_CROP_PATH, BASE_DIR / "logo-abaroasmart.png", LOGO_PATH]:
        if Path(path).exists():
            st.image(str(path), width=width)
            return

# ── TEMA PREMIUM ──────────────────────────────────────────────────────────────
def apply_theme():
    st.html("""
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>

    /* ══════════════════════════════════════════
       BASE & RESET
    ══════════════════════════════════════════ */
    *, *::before, *::after { box-sizing: border-box; }

    html, body, [data-testid="stAppViewContainer"], .stApp {
        font-family: 'Outfit', 'Segoe UI', sans-serif !important;
        background: #060d1a !important;
        color: #e2e8f0 !important;
    }

    /* Fondo con gradiente sutil tipo "aurora" */
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(ellipse 80% 50% at 20% -10%, rgba(37,99,235,.12) 0%, transparent 60%),
            radial-gradient(ellipse 60% 40% at 80% 110%, rgba(5,150,105,.07) 0%, transparent 55%),
            #060d1a !important;
    }

    /* Ocultar elementos de Streamlit */
    header[data-testid="stHeader"]   { display:none !important; }
    [data-testid="stToolbar"]         { display:none !important; }
    #MainMenu, footer                 { visibility:hidden !important; }

    /* Contenedor principal */
    .block-container {
        max-width: 100% !important;
        padding: .75rem 1.25rem 3rem 1.25rem !important;
    }

    /* ══════════════════════════════════════════
       TIPOGRAFÍA
    ══════════════════════════════════════════ */
    h1, h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3 {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
        color: #f1f5f9 !important;
        letter-spacing: -.02em !important;
    }
    .stApp p, .stApp span, .stApp label { font-family: 'Outfit', sans-serif !important; }
    [data-testid="stMetricValue"] { font-family: 'Outfit', sans-serif !important; font-weight: 800 !important; color: #f1f5f9 !important; }
    [data-testid="stMetricLabel"] { font-family: 'Outfit', sans-serif !important; color: #94a3b8 !important; font-weight: 500 !important; }

    /* ══════════════════════════════════════════
       SIDEBAR PREMIUM
    ══════════════════════════════════════════ */
    [data-testid="stSidebar"] {
        background: rgba(10,16,35,.97) !important;
        border-right: 1px solid rgba(255,255,255,.06) !important;
        backdrop-filter: blur(20px) !important;
    }
    [data-testid="stSidebar"] > div:first-child { background: transparent !important; }

    .sidebar-brand {
        padding: .6rem .4rem 1rem .4rem;
        border-bottom: 1px solid rgba(255,255,255,.06);
        margin-bottom: .75rem;
    }
    .sidebar-brand-logo {
        font-family: 'Outfit', sans-serif;
        font-size: 1.15rem;
        font-weight: 800;
        color: #f8fafc;
        letter-spacing: -.03em;
        line-height: 1;
    }
    .sidebar-brand-logo span { color: #3b82f6; }
    .sidebar-brand-sub {
        font-family: 'Outfit', sans-serif;
        font-size: .72rem;
        color: #475569;
        font-weight: 500;
        margin-top: .3rem;
        letter-spacing: .04em;
        text-transform: uppercase;
    }
    .sidebar-section {
        font-family: 'Outfit', sans-serif;
        font-size: .65rem;
        font-weight: 700;
        color: #334155;
        text-transform: uppercase;
        letter-spacing: .1em;
        padding: .8rem .4rem .3rem .4rem;
    }

    [data-testid="stSidebar"] .stButton > button {
        font-family: 'Outfit', sans-serif !important;
        width: 100% !important;
        border-radius: 10px !important;
        min-height: 40px !important;
        font-size: .83rem !important;
        font-weight: 600 !important;
        text-align: left !important;
        padding: .4rem .75rem !important;
        border: 1px solid transparent !important;
        background: transparent !important;
        color: #94a3b8 !important;
        transition: all .15s ease !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(59,130,246,.1) !important;
        border-color: rgba(59,130,246,.2) !important;
        color: #e2e8f0 !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: rgba(37,99,235,.18) !important;
        border-color: rgba(59,130,246,.35) !important;
        color: #93c5fd !important;
    }

    /* ══════════════════════════════════════════
       HEADER APP SHELL
    ══════════════════════════════════════════ */
    .app-header {
        background: rgba(15,23,42,.7);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(255,255,255,.06);
        border-radius: 16px;
        padding: .65rem 1.1rem;
        margin-bottom: .9rem;
        display: flex;
        align-items: center;
        gap: .75rem;
    }
    .app-header-module {
        font-family: 'Outfit', sans-serif;
        font-size: .75rem;
        font-weight: 600;
        color: #475569;
        text-transform: uppercase;
        letter-spacing: .07em;
    }
    .app-header-title {
        font-family: 'Outfit', sans-serif;
        font-size: 1rem;
        font-weight: 700;
        color: #f1f5f9;
        letter-spacing: -.02em;
    }
    .header-breadcrumb {
        font-family: 'Outfit', sans-serif;
        font-size: .8rem;
        font-weight: 500;
        color: #475569;
        padding: .25rem .6rem;
        background: rgba(255,255,255,.04);
        border-radius: 8px;
        border: 1px solid rgba(255,255,255,.06);
        display: inline-block;
    }

    /* ══════════════════════════════════════════
       HERO / BANNER
    ══════════════════════════════════════════ */
    .hero-banner {
        background: linear-gradient(135deg,
            rgba(15,23,42,.95) 0%,
            rgba(17,24,50,.98) 50%,
            rgba(12,20,40,.95) 100%);
        border: 1px solid rgba(59,130,246,.15);
        border-radius: 20px;
        padding: 1.5rem 1.75rem;
        margin-bottom: 1.25rem;
        position: relative;
        overflow: hidden;
    }
    .hero-banner::before {
        content: '';
        position: absolute;
        top: -60%;
        right: -5%;
        width: 380px;
        height: 380px;
        background: radial-gradient(ellipse, rgba(37,99,235,.08) 0%, transparent 70%);
        pointer-events: none;
    }
    .hero-eyebrow {
        font-family: 'Outfit', sans-serif;
        font-size: .72rem;
        font-weight: 700;
        color: #3b82f6;
        text-transform: uppercase;
        letter-spacing: .1em;
        margin-bottom: .5rem;
    }
    .hero-title {
        font-family: 'Outfit', sans-serif;
        font-size: 1.55rem;
        font-weight: 800;
        color: #f8fafc;
        letter-spacing: -.03em;
        line-height: 1.15;
        margin-bottom: .4rem;
    }
    .hero-subtitle {
        font-family: 'Outfit', sans-serif;
        font-size: .88rem;
        color: #64748b;
        font-weight: 400;
        line-height: 1.5;
    }

    /* ══════════════════════════════════════════
       KPI CARDS
    ══════════════════════════════════════════ */
    .kpi-card {
        background: rgba(15,23,42,.8);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255,255,255,.07);
        border-radius: 18px;
        padding: 1.1rem 1.2rem;
        min-height: 108px;
        position: relative;
        overflow: hidden;
        transition: border-color .2s ease, transform .15s ease;
    }
    .kpi-card::after {
        content: '';
        position: absolute;
        top: 0; left: 0;
        right: 0; height: 2px;
        background: linear-gradient(90deg, transparent, var(--kpi-accent, #3b82f6), transparent);
        opacity: .6;
    }
    .kpi-card:hover {
        border-color: rgba(59,130,246,.2);
        transform: translateY(-1px);
    }
    .kpi-icon {
        font-size: 1.1rem;
        margin-bottom: .4rem;
        opacity: .8;
        display: block;
    }
    .kpi-label {
        font-family: 'Outfit', sans-serif;
        font-size: .72rem;
        font-weight: 700;
        color: #475569;
        text-transform: uppercase;
        letter-spacing: .08em;
        margin-bottom: .35rem;
    }
    .kpi-value {
        font-family: 'Outfit', sans-serif;
        font-size: 1.65rem;
        font-weight: 800;
        color: #f1f5f9;
        letter-spacing: -.03em;
        line-height: 1;
        margin-bottom: .3rem;
    }
    .kpi-delta {
        font-family: 'Outfit', sans-serif;
        font-size: .78rem;
        font-weight: 600;
        color: #64748b;
    }
    .kpi-delta.positive { color: #34d399; }
    .kpi-delta.warning  { color: #fb923c; }

    /* ══════════════════════════════════════════
       PANEL / SECTION CARDS
    ══════════════════════════════════════════ */
    .section-card {
        background: rgba(15,23,42,.7);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,.07);
        border-radius: 18px;
        padding: 1.2rem 1.3rem;
        margin-bottom: 1rem;
    }
    .section-title {
        font-family: 'Outfit', sans-serif;
        font-size: .95rem;
        font-weight: 700;
        color: #f1f5f9;
        letter-spacing: -.01em;
        margin-bottom: .2rem;
    }
    .section-subtitle {
        font-family: 'Outfit', sans-serif;
        font-size: .8rem;
        color: #475569;
        margin-bottom: .9rem;
    }

    /* ══════════════════════════════════════════
       FORM STYLING
    ══════════════════════════════════════════ */
    /* Sección de formulario */
    .form-section {
        background: rgba(15,23,42,.6);
        border: 1px solid rgba(255,255,255,.07);
        border-radius: 16px;
        padding: 1.1rem 1.2rem 1rem 1.2rem;
        margin-bottom: .85rem;
    }
    .form-section-header {
        font-family: 'Outfit', sans-serif;
        font-size: .72rem;
        font-weight: 700;
        color: #3b82f6;
        text-transform: uppercase;
        letter-spacing: .1em;
        margin-bottom: .75rem;
        padding-bottom: .5rem;
        border-bottom: 1px solid rgba(59,130,246,.12);
        display: flex;
        align-items: center;
        gap: .4rem;
    }

    /* Labels de inputs */
    div[data-testid="stTextInput"] label,
    div[data-testid="stNumberInput"] label,
    div[data-testid="stSelectbox"] label,
    div[data-testid="stDateInput"] label,
    div[data-testid="stTextArea"] label,
    div[data-testid="stCheckbox"] label {
        font-family: 'Outfit', sans-serif !important;
        font-size: .8rem !important;
        font-weight: 600 !important;
        color: #94a3b8 !important;
        text-transform: uppercase !important;
        letter-spacing: .06em !important;
    }

    /* Inputs */
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input {
        font-family: 'Outfit', sans-serif !important;
        font-size: .9rem !important;
        font-weight: 500 !important;
        background: rgba(15,23,42,.8) !important;
        border: 1.5px solid rgba(255,255,255,.1) !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
        padding: .55rem .9rem !important;
        transition: border-color .15s ease !important;
    }
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stNumberInput"] input:focus {
        border-color: rgba(59,130,246,.5) !important;
        box-shadow: 0 0 0 3px rgba(59,130,246,.1) !important;
    }
    div[data-testid="stTextInput"] input::placeholder { color: #334155 !important; }
    div[data-testid="stTextInput"] input:disabled {
        opacity: .5 !important;
        cursor: not-allowed !important;
    }

    /* Selectbox */
    div[data-testid="stSelectbox"] > div > div {
        font-family: 'Outfit', sans-serif !important;
        font-size: .9rem !important;
        background: rgba(15,23,42,.8) !important;
        border: 1.5px solid rgba(255,255,255,.1) !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
    }
    div[data-testid="stSelectbox"] > div > div:focus-within {
        border-color: rgba(59,130,246,.5) !important;
        box-shadow: 0 0 0 3px rgba(59,130,246,.1) !important;
    }

    /* TextArea */
    div[data-testid="stTextArea"] textarea {
        font-family: 'Outfit', sans-serif !important;
        font-size: .88rem !important;
        background: rgba(15,23,42,.8) !important;
        border: 1.5px solid rgba(255,255,255,.1) !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
        transition: border-color .15s ease !important;
    }
    div[data-testid="stTextArea"] textarea:focus {
        border-color: rgba(59,130,246,.5) !important;
        box-shadow: 0 0 0 3px rgba(59,130,246,.1) !important;
    }

    /* Date input */
    div[data-testid="stDateInput"] input {
        font-family: 'Outfit', sans-serif !important;
        background: rgba(15,23,42,.8) !important;
        border: 1.5px solid rgba(255,255,255,.1) !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
    }

    /* ══════════════════════════════════════════
       BOTONES
    ══════════════════════════════════════════ */
    .stButton > button {
        font-family: 'Outfit', sans-serif !important;
        font-size: .84rem !important;
        font-weight: 700 !important;
        border-radius: 12px !important;
        min-height: 42px !important;
        letter-spacing: .01em !important;
        transition: all .15s ease !important;
        white-space: nowrap !important;
    }
    /* Botón primario */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1d4ed8, #2563eb) !important;
        border: 1px solid rgba(96,165,250,.3) !important;
        color: white !important;
        box-shadow: 0 4px 15px rgba(37,99,235,.25) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #2563eb, #3b82f6) !important;
        box-shadow: 0 6px 20px rgba(37,99,235,.35) !important;
        transform: translateY(-1px) !important;
    }
    /* Botón secundario */
    .stButton > button[kind="secondary"] {
        background: rgba(30,41,59,.8) !important;
        border: 1.5px solid rgba(255,255,255,.1) !important;
        color: #cbd5e1 !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background: rgba(51,65,85,.8) !important;
        border-color: rgba(255,255,255,.18) !important;
        color: #f1f5f9 !important;
    }

    /* Download buttons */
    div[data-testid="stDownloadButton"] button {
        font-family: 'Outfit', sans-serif !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
    }

    /* ══════════════════════════════════════════
       DATAFRAMES / TABLAS
    ══════════════════════════════════════════ */
    div[data-testid="stDataFrame"] {
        border-radius: 14px !important;
        overflow: hidden !important;
        border: 1px solid rgba(255,255,255,.07) !important;
    }
    div[data-testid="stDataFrame"] iframe {
        border-radius: 14px !important;
    }

    /* ══════════════════════════════════════════
       EXPANDERS
    ══════════════════════════════════════════ */
    div[data-testid="stExpander"] {
        background: rgba(15,23,42,.6) !important;
        border: 1px solid rgba(255,255,255,.07) !important;
        border-radius: 14px !important;
        overflow: hidden !important;
        margin-bottom: .5rem !important;
    }
    div[data-testid="stExpander"] summary {
        font-weight: 600 !important;
        color: #94a3b8 !important;
        font-size: .88rem !important;
        padding: .75rem 1rem !important;
    }
    /* Solo el texto del summary, sin tocar el ícono de flecha */
    div[data-testid="stExpander"] summary span:last-child {
        font-family: 'Outfit', sans-serif !important;
    }
    div[data-testid="stExpander"] summary:hover { color: #e2e8f0 !important; }

    /* ══════════════════════════════════════════
       TABS
    ══════════════════════════════════════════ */
    div[data-testid="stTabs"] [role="tablist"] {
        border-bottom: 1px solid rgba(255,255,255,.07) !important;
        gap: .25rem !important;
    }
    div[data-testid="stTabs"] button[role="tab"] {
        font-family: 'Outfit', sans-serif !important;
        font-size: .84rem !important;
        font-weight: 600 !important;
        color: #475569 !important;
        border-radius: 8px 8px 0 0 !important;
        padding: .5rem 1rem !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: #60a5fa !important;
        border-bottom: 2px solid #3b82f6 !important;
    }

    /* ══════════════════════════════════════════
       ALERTS / INFO / WARNING / SUCCESS
    ══════════════════════════════════════════ */
    div[data-testid="stAlert"] {
        font-family: 'Outfit', sans-serif !important;
        border-radius: 12px !important;
        font-size: .88rem !important;
        font-weight: 500 !important;
    }

    /* ══════════════════════════════════════════
       STATUS PILLS
    ══════════════════════════════════════════ */
    .pill {
        display: inline-flex;
        align-items: center;
        gap: .3rem;
        padding: .2rem .6rem;
        border-radius: 999px;
        font-family: 'Outfit', sans-serif;
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .04em;
    }
    .pill-blue    { background: rgba(59,130,246,.15);  color: #93c5fd;  border: 1px solid rgba(59,130,246,.2); }
    .pill-green   { background: rgba(52,211,153,.15);  color: #6ee7b7;  border: 1px solid rgba(52,211,153,.2); }
    .pill-amber   { background: rgba(251,191,36,.12);  color: #fcd34d;  border: 1px solid rgba(251,191,36,.2); }
    .pill-red     { background: rgba(239,68,68,.12);   color: #fca5a5;  border: 1px solid rgba(239,68,68,.2); }
    .pill-slate   { background: rgba(100,116,139,.12); color: #94a3b8;  border: 1px solid rgba(100,116,139,.2); }
    .pill-purple  { background: rgba(167,139,250,.12); color: #c4b5fd;  border: 1px solid rgba(167,139,250,.2); }

    /* ══════════════════════════════════════════
       DIVIDERS
    ══════════════════════════════════════════ */
    hr {
        border: none !important;
        border-top: 1px solid rgba(255,255,255,.06) !important;
        margin: 1rem 0 !important;
    }

    /* ══════════════════════════════════════════
       QUICK ACCESS SHORTCUTS
    ══════════════════════════════════════════ */
    .shortcut-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: .5rem;
    }
    .shortcut-btn {
        background: rgba(15,23,42,.8);
        border: 1.5px solid rgba(255,255,255,.07);
        border-radius: 14px;
        padding: .75rem 1rem;
        display: flex;
        align-items: center;
        gap: .6rem;
        cursor: pointer;
        transition: all .15s ease;
        text-decoration: none;
    }
    .shortcut-btn:hover {
        background: rgba(37,99,235,.12);
        border-color: rgba(59,130,246,.25);
        transform: translateY(-1px);
    }
    .shortcut-icon { font-size: 1.2rem; }
    .shortcut-label {
        font-family: 'Outfit', sans-serif;
        font-size: .84rem;
        font-weight: 600;
        color: #cbd5e1;
    }

    /* ══════════════════════════════════════════
       HEADER BOTONES NAV
    ══════════════════════════════════════════ */
    .stButton > button[data-key^="hq_"] {
        font-size: .78rem !important;
        min-height: 36px !important;
        padding: .25rem .6rem !important;
        border-radius: 10px !important;
    }
    .stButton > button[data-key="toggle_sidebar"] {
        min-height: 36px !important;
        border-radius: 10px !important;
        font-size: 1rem !important;
    }

    /* ══════════════════════════════════════════
       MOBILE RESPONSIVE ≤768px
    ══════════════════════════════════════════ */
    @media (max-width: 768px) {
        .block-container { padding: .4rem .5rem 4rem .5rem !important; }
        .hero-title { font-size: 1.2rem; }
        .kpi-value  { font-size: 1.3rem; }
        .kpi-card   { min-height: 85px; padding: .75rem .9rem; border-radius: 14px; }

        /* Sidebar móvil: cajón tipo overlay, Streamlit lo controla */
        section[data-testid="stSidebar"] {
            width: 82vw !important; max-width: 300px !important;
            position: fixed !important;
            top: 0 !important; left: 0 !important; bottom: 0 !important;
            z-index: 999 !important;
        }
        /* Botón nativo de Streamlit visible en móvil */
        [data-testid="collapsedControl"] {
            display: flex !important;
            position: fixed !important;
            top: .5rem !important; left: .5rem !important;
            z-index: 1000 !important;
        }

        div[data-testid="stDataFrame"] { overflow-x: auto; -webkit-overflow-scrolling: touch; }
        div[data-testid="stDownloadButton"] button { width: 100% !important; }
        .hero-banner::before { display: none; }
        .hero-banner { padding: 1rem 1.1rem; }
    }

    /* ══════════════════════════════════════════
       TABLET 769-1024px
    ══════════════════════════════════════════ */
    @media (min-width: 769px) and (max-width: 1024px) {
        .block-container { padding-left: .8rem !important; padding-right: .8rem !important; }
        .kpi-value { font-size: 1.45rem; }
    }

    </style>
    """)


# ── Componentes HTML ──────────────────────────────────────────────────────────

def form_section(title: str, icon: str = ""):
    """Cabecera visual de sección dentro de un formulario."""
    prefix = f"{icon} " if icon else ""
    st.markdown(f"""
    <div class="form-section-header">{prefix}{title}</div>
    """, unsafe_allow_html=True)


def section_header(title: str, subtitle: str = "", icon: str = ""):
    """Título de sección con subtítulo opcional."""
    icon_html = f'<span style="font-size:1.15rem;margin-right:.4rem;">{icon}</span>' if icon else ""
    sub_html = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(f"""
    <div class="section-card" style="padding:.9rem 1.1rem .6rem 1.1rem; margin-bottom:.6rem;">
        <div class="section-title">{icon_html}{title}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def pill(text: str, variant: str = "blue") -> str:
    """Retorna HTML de una pill de estado."""
    return f'<span class="pill pill-{variant}">{text}</span>'


def dashboard_kpi_card(label: str, value: str, delta: str = "",
                       icon: str = "", accent: str = "#3b82f6",
                       delta_class: str = ""):
    """KPI card premium con ícono, acento de color y delta."""
    icon_html = f'<span class="kpi-icon">{icon}</span>' if icon else ""
    delta_html = f'<div class="kpi-delta {delta_class}">{delta}</div>' if delta else ""
    st.markdown(f"""
    <div class="kpi-card" style="--kpi-accent:{accent};">
        {icon_html}
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


# ── PDF Cotización ────────────────────────────────────────────────────────────
def make_quote_pdf(quote_number, quote_date, client_row, vendor_name,
                   product_lines, kit_lines, service_lines, supply_lines,
                   notes, subtotal_products, subtotal_kits, subtotal_services,
                   subtotal_supplies, vat_products, total):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    navy  = colors.HexColor("#23356d")
    blue  = colors.HexColor("#0b4f94")
    light = colors.HexColor("#3f69b8")

    c.setFillColor(blue)
    c.rect(0, height - 88, width, 88, fill=1, stroke=0)
    logo_path = _pdf_logo_path()
    if logo_path:
        try:
            c.drawImage(str(logo_path), 42, height - 66, width=150, height=32, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(205, height - 40, "Abaroa Smart – Domótica y Automatización")
    c.setFont("Helvetica", 9)
    c.drawString(205, height - 54, "WhatsApp: +56 9 8183 8679  |  contacto@abaroasmart.com")
    c.drawString(205, height - 68, "www.abaroasmart.com  |  Osorno, Región de Los Lagos")
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(width / 2, height - 118, "Cotización")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(42, height - 142, f"N° Cotización: {quote_number}")
    c.setFont("Helvetica", 10)
    c.drawString(42, height - 156, f"Fecha: {str(quote_date)[:10]}")
    c.drawString(42, height - 170, f"Ejecutivo: {vendor_name or 'Abaroa Smart'}")
    y = height - 178
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Datos del Cliente")
    c.drawString(width / 2 + 20, y, "Abaroa Smart")
    c.setFont("Helvetica", 10)
    left_lines = [str(client_row.get("name","")), str(client_row.get("address","") or ""), str(client_row.get("phone","") or ""), str(client_row.get("email","") or "")]
    right_lines = ["Abaroa Smart", f"Ejecutivo: {vendor_name or 'Abaroa Smart'}", "Osorno, Región de Los Lagos", "contacto@abaroasmart.com"]
    yl = y - 18
    for line in left_lines:
        c.drawString(50, yl, str(line)[:42]); yl -= 14
    yr = y - 18
    for line in right_lines:
        c.drawString(width / 2 + 20, yr, str(line)[:42]); yr -= 14
    rows = []
    for x in product_lines:
        rows.append((x["description"], int(x["quantity"]), int(x["unit_price"]), int(x["line_total"])))
    for x in kit_lines:
        rows.append((x.get("name", x.get("description","")), int(x["quantity"]), int(x["unit_price"]), int(x["line_total"])))
    for x in service_lines:
        rows.append((f"Servicio · {x['description']}", int(x["quantity"]), int(x["unit_price"]), int(x["line_total"])))
    for x in supply_lines:
        rows.append((f"Insumo · {x['description']}", int(x["quantity"]), int(x["unit_price"]), int(x["line_total"])))
    table_w, table_x, table_top, col_widths, row_h = 500, (width - 500) / 2, height - 314, [250,70,90,90], 26
    c.setFillColor(light)
    c.rect(table_x, table_top, table_w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    cx = table_x
    for h_txt, w in zip(["Producto / Servicio","Cantidad","Precio unit.","Subtotal"], col_widths):
        c.drawCentredString(cx + w / 2, table_top + 8, h_txt); cx += w
    yrow = table_top - row_h
    c.setFont("Helvetica", 9)
    for desc, qty, unit, subtotal in (rows[:12] or [("(sin ítems)",0,0,0)]):
        cx = table_x
        c.setFillColor(colors.white)
        for w in col_widths:
            c.rect(cx, yrow, w, row_h, fill=1, stroke=1); cx += w
        c.setFillColor(colors.black)
        c.drawString(table_x + 6, yrow + 8, str(desc)[:40])
        c.drawCentredString(table_x + col_widths[0] + col_widths[1] / 2, yrow + 8, str(qty))
        c.drawCentredString(table_x + col_widths[0] + col_widths[1] + col_widths[2] / 2, yrow + 8, money(unit))
        c.drawCentredString(table_x + sum(col_widths[:3]) + col_widths[3] / 2, yrow + 8, money(subtotal))
        yrow -= row_h
    ty, label_x, value_x = yrow - 16, width - 175, width - 42
    c.setFillColor(navy)
    c.setFont("Helvetica", 10)
    c.drawRightString(label_x, ty, "Total afecto IVA");       c.drawRightString(value_x, ty, money(int(subtotal_products + subtotal_kits + subtotal_supplies)))
    c.drawRightString(label_x, ty - 16, "Total exento");      c.drawRightString(value_x, ty - 16, money(int(subtotal_services)))
    c.drawRightString(label_x, ty - 32, "IVA 19%");           c.drawRightString(value_x, ty - 32, money(vat_products))
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(label_x, ty - 54, "TOTAL");             c.drawRightString(value_x, ty - 54, money(total))
    footer_lines = [
        "• Productos, kits e insumos afectos a IVA. Servicios exentos de IVA.",
        "• Condición de Pago: 50% anticipo, 50% contra entrega.",
        "• Garantía: 6 meses en instalación y configuración. www.abaroasmart.com",
    ]
    if notes:
        for line in str(notes).splitlines()[:2]:
            if line.strip(): footer_lines.append(f"• {line.strip()}")
    c.setFont("Helvetica", 7.5)
    txt = c.beginText(42, 90)
    txt.setLeading(10)
    for raw in footer_lines:
        words, line = raw.split(), ""
        for word in words:
            test = (line + " " + word).strip()
            if c.stringWidth(test, "Helvetica", 7.5) <= (width - 84):
                line = test
            else:
                txt.textLine(line); line = word
        if line: txt.textLine(line)
    c.drawText(txt)
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


# ── PDF Acta de entrega ───────────────────────────────────────────────────────
def make_project_delivery_pdf(project_id):
    from database import get_conn
    conn = get_conn()
    project = conn.execute("""
        SELECT p.*, c.name AS client_name, c.address AS client_address,
               c.phone AS client_phone, c.email AS client_email, q.quote_number
        FROM projects p LEFT JOIN clients c ON c.id=p.client_id
        LEFT JOIN quotes q ON q.id=p.quotation_id WHERE p.id=?
    """, (project_id,)).fetchone()
    if not project: conn.close(); return None
    items = conn.execute("SELECT * FROM project_items WHERE project_id=? AND item_type IN ('producto','kit_component','insumo') ORDER BY id", (project_id,)).fetchall()
    checklist = conn.execute("""
        SELECT pci.item_text, pci.is_checked, pci.evidence_note
        FROM project_checklists pc JOIN project_checklist_items pci ON pci.project_checklist_id=pc.id
        WHERE pc.project_id=? ORDER BY pci.id
    """, (project_id,)).fetchall()
    conn.close()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    navy = colors.HexColor("#23356d"); blue = colors.HexColor("#0b4f94"); light = colors.HexColor("#3f69b8")
    c.setFillColor(colors.whitesmoke); c.rect(0,0,width,height,fill=1,stroke=0)
    c.setFillColor(blue); c.rect(0,height-88,width,88,fill=1,stroke=0)
    logo_path = _pdf_logo_path()
    if logo_path:
        try: c.drawImage(str(logo_path),42,height-66,width=150,height=32,preserveAspectRatio=True,mask="auto")
        except Exception: pass
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold",11)
    c.drawString(205,height-40,"Abaroa Smart – Domótica y Automatización")
    c.setFont("Helvetica",9)
    c.drawString(205,height-54,"WhatsApp: +56 9 8183 8679  |  contacto@abaroasmart.com")
    c.drawString(205,height-68,"www.abaroasmart.com  |  Osorno, Región de Los Lagos")
    c.setFillColor(navy); c.setFont("Helvetica-Bold",26); c.drawCentredString(width/2,height-118,"Acta de Entrega")
    y = height-175
    c.setFont("Helvetica-Bold",12); c.drawString(50,y,"Datos del Cliente"); c.drawString(width/2+20,y,"Datos del Proyecto")
    c.setFont("Helvetica",10)
    left = [str(project["client_name"] or ""),str(project["client_address"] or ""),str(project["client_phone"] or ""),str(project["client_email"] or "")]
    right = [f"N° Proyecto: {project['project_number'] or '-'}",f"Cotización: {project['quote_number'] or '-'}",f"Instalación: {project['installation_date'] or '-'}",f"Entrega: {project['delivery_date'] or '-'}"]
    yl = y-18
    for line in left: c.drawString(50,yl,str(line)[:42]); yl -= 14
    yr = y-18
    for line in right: c.drawString(width/2+20,yr,str(line)[:42]); yr -= 14
    table_w, table_x = 500, (width-500)/2; table_top = height-310; col_w = [280,70,70,80]; row_h = 24
    c.setFillColor(light); c.rect(table_x,table_top,table_w,row_h,fill=1,stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold",10)
    cx = table_x
    for h_txt,w in zip(["Ítem","SKU","Comprado","Usado"],col_w):
        c.drawCentredString(cx+w/2,table_top+7,h_txt); cx += w
    yrow = table_top-row_h; c.setFont("Helvetica",9)
    for item in (items[:14] if items else []):
        cx = table_x; c.setFillColor(colors.white)
        for w in col_w: c.rect(cx,yrow,w,row_h,fill=1,stroke=1); cx += w
        c.setFillColor(colors.black)
        c.drawString(table_x+6,yrow+7,str(item["description"] or "")[:45])
        c.drawCentredString(table_x+col_w[0]+col_w[1]/2,yrow+7,str(item["sku"] or "")[:10])
        c.drawCentredString(table_x+col_w[0]+col_w[1]+col_w[2]/2,yrow+7,str(int(item["quantity"] or 0)))
        c.drawCentredString(table_x+sum(col_w[:3])+col_w[3]/2,yrow+7,str(int(item["used_quantity"] or 0)))
        yrow -= row_h
    ycl = yrow-20; c.setFont("Helvetica-Bold",11); c.setFillColor(navy); c.drawString(50,ycl,"Checklist de entrega")
    ycl -= 16; c.setFont("Helvetica",9)
    for cl_item in (checklist[:10] if checklist else []):
        mark = "✓" if cl_item["is_checked"] else "○"
        c.drawString(50,ycl,f"{mark} {str(cl_item['item_text'] or '')[:80]}"); ycl -= 13
        if ycl < 100: break
    sig_y = 80; c.setFillColor(navy); c.setFont("Helvetica",9)
    c.line(50,sig_y+20,220,sig_y+20); c.drawString(50,sig_y+6,"Firma cliente")
    c.line(width-220,sig_y+20,width-50,sig_y+20); c.drawString(width-220,sig_y+6,"Firma técnico Abaroa Smart")
    c.save(); buffer.seek(0); return buffer.getvalue()


# ── PDF genérico ──────────────────────────────────────────────────────────────
def make_pdf(title, subtitle="", sections=None):
    sections = sections or []
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 40
    logo_path = _pdf_logo_path()
    if logo_path:
        try: c.drawImage(str(logo_path),40,y-35,width=140,height=35,preserveAspectRatio=True,mask="auto")
        except Exception: pass
    c.setFont("Helvetica-Bold",18); c.drawString(40,y-55,title); y -= 75
    if subtitle: c.setFont("Helvetica",10); c.drawString(40,y,subtitle); y -= 20
    for section_title, lines in sections:
        if y < 80: c.showPage(); y = height-40
        c.setFont("Helvetica-Bold",12); c.drawString(40,y,section_title); y -= 16
        c.setFont("Helvetica",10)
        for line in lines:
            if y < 60: c.showPage(); y = height-40; c.setFont("Helvetica",10)
            c.drawString(50,y,str(line)[:110]); y -= 14
        y -= 8
    c.save(); buffer.seek(0); return buffer.getvalue()
