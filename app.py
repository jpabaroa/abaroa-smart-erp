"""
app.py — Abaroa Smart ERP
Entry point: configuración, tema premium, sidebar y despachador de vistas.

CORRECCIONES v2:
  - inject_sidebar_css: st.html() → st.markdown(unsafe_allow_html=True) para que
    el CSS realmente aplique a la página (st.html crea un iframe aislado en Streamlit ≥1.36)
  - render_header: eliminado parámetro value= en st.text_input que causaba
    StreamlitAPIException cuando global_search ya existía en session_state
  - CSS sidebar móvil: mejorado para landscape y pantallas pequeñas
"""

import streamlit as st
from utils import apply_theme, logo
from database import (
    init_db, ensure_app_settings, recalc_all_sale_prices, recalc_stock,
    remove_duplicate_rows, get_alerts_data, admin_logged_in,
    verify_admin_credentials, get_setting,
)

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Abaroa Smart ERP",
    layout="wide",
    page_icon="💡",
    initial_sidebar_state="expanded",
)
apply_theme()
init_db()
ensure_app_settings()
remove_duplicate_rows()
recalc_all_sale_prices()
recalc_stock()

# ── Session state ─────────────────────────────────────────────────────────────
if "current_tab"   not in st.session_state: st.session_state["current_tab"]   = "Inicio"
if "sidebar_open"  not in st.session_state: st.session_state["sidebar_open"]  = True
if "global_search" not in st.session_state: st.session_state["global_search"] = ""

# ── CSS sidebar open/close ────────────────────────────────────────────────────
# FIX: usar st.markdown() en lugar de st.html() para que los estilos apliquen
# globalmente. st.html() en Streamlit ≥1.36 renderiza en un <iframe> aislado
# y el CSS nunca sale de ese iframe.

def inject_sidebar_css(open_: bool = True):
    """
    Controla la visibilidad del sidebar via JS → window.parent.document.
    Mismo mecanismo que apply_theme(): bypasea el sanitizador HTML de Streamlit
    y el scoping de iframe de st.html().
    """
    import streamlit.components.v1 as components

    if open_:
        css = """
        @media (min-width: 769px) {
            [data-testid="collapsedControl"] { display:none !important; }
            section[data-testid="stSidebar"] {
                width:17rem !important; min-width:17rem !important;
                transform:translateX(0) !important;
                opacity:1 !important; visibility:visible !important;
                transition: transform .25s ease, opacity .2s ease;
            }
        }
        @media (max-width: 768px) {
            [data-testid="collapsedControl"] { display:none !important; }
            section[data-testid="stSidebar"] {
                position:fixed !important;
                top:0 !important; left:0 !important; bottom:0 !important;
                height:100dvh !important;
                width:85vw !important; max-width:320px !important;
                z-index:9999 !important;
                transform:translateX(0) !important;
                opacity:1 !important; visibility:visible !important;
                box-shadow:4px 0 24px rgba(0,0,0,.5) !important;
                transition: transform .25s ease;
            }
        }
        @media (max-height: 500px) and (orientation: landscape) {
            section[data-testid="stSidebar"] {
                position:fixed !important;
                top:0 !important; left:0 !important; bottom:0 !important;
                height:100dvh !important; width:260px !important;
                z-index:9999 !important;
                transform:translateX(0) !important;
                overflow-y:auto !important;
            }
        }
        /* Nuclear: ocultar botón nativo a toda resolución */
        [data-testid="collapsedControl"],
        button[data-testid="collapsedControl"] {
            display:none !important; visibility:hidden !important;
            opacity:0 !important; width:0 !important; height:0 !important;
            overflow:hidden !important; pointer-events:none !important;
            font-size:0 !important;
        }
        """
    else:
        css = """
        @media (min-width: 769px) {
            [data-testid="collapsedControl"] { display:none !important; }
            section[data-testid="stSidebar"] {
                width:0 !important; min-width:0 !important; max-width:0 !important;
                overflow:hidden !important;
                transform:translateX(-100%) !important;
                opacity:0 !important; visibility:hidden !important;
                transition: transform .25s ease, opacity .2s ease;
            }
            [data-testid="stAppViewContainer"] > .main { margin-left:0 !important; }
        }
        @media (max-width: 768px) {
            [data-testid="collapsedControl"] { display:none !important; }
            section[data-testid="stSidebar"] {
                position:fixed !important;
                top:0 !important; left:0 !important; bottom:0 !important;
                height:100dvh !important;
                width:85vw !important; max-width:320px !important;
                z-index:9999 !important;
                transform:translateX(-110%) !important;
                opacity:0 !important; visibility:hidden !important;
                transition: transform .25s ease, opacity .2s ease;
            }
        }
        @media (max-height: 500px) and (orientation: landscape) {
            section[data-testid="stSidebar"] {
                transform:translateX(-110%) !important;
                opacity:0 !important; visibility:hidden !important;
            }
        }
        """

    css_js = css.replace("\\", "\\\\").replace("`", "\\`")
    components.html(
        f"""<script>
        (function() {{
          var el = window.parent.document.getElementById('_erp_sidebar_css');
          if (!el) {{
            el = window.parent.document.createElement('style');
            el.id = '_erp_sidebar_css';
            window.parent.document.head.appendChild(el);
          }}
          el.textContent = `{css_js}`;
        }})();
        </script>""",
        height=0,
        scrolling=False,
    )


inject_sidebar_css(st.session_state.get("sidebar_open", True))


# ── HEADER ────────────────────────────────────────────────────────────────────
def render_header():
    current_tab = st.session_state["current_tab"]
    h1, h2, h3, h4, h5 = st.columns([0.5, 3.2, 6, 0.65, 0.65])

    with h1:
        lbl = "✕" if st.session_state.get("sidebar_open", True) else "☰"
        if st.button(lbl, key="toggle_sidebar", use_container_width=True):
            st.session_state["sidebar_open"] = not st.session_state.get("sidebar_open", True)
            st.rerun()

    with h2:
        # FIX: no pasar value= junto con key= apuntando al mismo session_state.
        # Streamlit lanza StreamlitAPIException si la clave ya existe en session_state
        # y además se pasa value=. Solo se usa key= y Streamlit gestiona el valor.
        st.text_input(
            "Buscar",
            key="global_search",
            label_visibility="collapsed",
            placeholder="🔎 Buscar clientes, SKU, OT...",
        )

    with h3:
        quick = [("Inicio","🏠"), ("Cotización","🧾"), ("Inventario","📦"), ("Proyectos","🛠️"), ("OT","📋")]
        cols = st.columns(len(quick))
        for col, (tab, icon) in zip(cols, quick):
            with col:
                btype = "primary" if current_tab == tab else "secondary"
                if st.button(f"{icon} {tab}", key=f"hq_{tab}", use_container_width=True, type=btype):
                    st.session_state["current_tab"] = tab
                    st.rerun()

    with h4:
        alerts = get_alerts_data()
        bell   = f"🔔 {len(alerts)}" if alerts else "🔔"
        with st.popover(bell, use_container_width=True):
            st.markdown("**Alertas del sistema**")
            if alerts:
                for a in alerts:
                    fn = st.warning if a["level"] == "warning" else st.info
                    fn(f"**{a['title']}**\n\n{a['detail']}")
            else:
                st.success("Sin alertas activas.")

    with h5:
        with st.popover("👤", use_container_width=True):
            if admin_logged_in():
                st.success(f"**{get_setting('admin_username','admin')}**")
                if st.button("Panel admin", key="hdr_admin_go"):
                    st.session_state["current_tab"] = "Administración"
                    st.rerun()
                if st.button("Cerrar sesión", key="hdr_logout"):
                    st.session_state["admin_logged_in"] = False
                    st.rerun()
            else:
                pu = st.text_input("Usuario",    key="hdr_user")
                pp = st.text_input("Contraseña", type="password", key="hdr_pass")
                if st.button("Ingresar", key="hdr_login"):
                    if verify_admin_credentials(pu, pp):
                        st.session_state["admin_logged_in"] = True
                        st.rerun()
                    else:
                        st.error("Credenciales incorrectas.")
                st.caption("Default: admin / admin123")

    # Breadcrumb
    st.markdown(f"""
    <div class="app-header">
      <div>
        <div class="app-header-module">Abaroa Smart ERP</div>
        <div class="app-header-title">{current_tab}</div>
      </div>
    </div>""", unsafe_allow_html=True)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
def render_sidebar():
    if not st.session_state.get("sidebar_open", True):
        return

    nav = {
        "Principal":  [("Inicio","🏠 Inicio"), ("Flujo Guiado","🧭 Flujo Guiado"), ("Buscador","🔎 Buscador")],
        "Operación":  [("Proyectos","🛠️ Proyectos"), ("OT","📋 OT"), ("Garantías","🛡️ Garantías")],
        "Comercial":  [("Cotización","🧾 Cotización"), ("Historial Cotizaciones","📚 Historial"),
                       ("Ventas","💳 Ventas"), ("Facturación","🧮 Facturación")],
        "Inventario": [("Inventario","📦 Inventario"), ("Herramientas","🔧 Herramientas"),
                       ("Insumos","🧰 Insumos"), ("Kits","🧩 Kits"), ("Proveedores","🚚 Proveedores")],
        "CRM":        [("Clientes","👤 Clientes"), ("Vendedores","🤝 Vendedores")],
        "Sistema":    [("Respaldo y Restauración","⚙️ Respaldos"), ("Administración","🔐 Admin")],
    }

    with st.sidebar:
        st.markdown("""
        <div class="sidebar-brand">
          <div class="sidebar-brand-logo">Abaroa<span>Smart</span></div>
          <div class="sidebar-brand-sub">ERP Operativo</div>
        </div>""", unsafe_allow_html=True)

        current = st.session_state.get("current_tab", "Inicio")
        for section, items in nav.items():
            st.markdown(f'<div class="sidebar-section">{section}</div>', unsafe_allow_html=True)
            for tab_key, tab_label in items:
                btype = "primary" if current == tab_key else "secondary"
                if st.button(tab_label, key=f"nav_{tab_key}", use_container_width=True, type=btype):
                    st.session_state["current_tab"] = tab_key
                    st.rerun()


# ── Render ────────────────────────────────────────────────────────────────────
render_header()
render_sidebar()
current_tab = st.session_state.get("current_tab", "Inicio")

# ── Dispatcher ────────────────────────────────────────────────────────────────
_views = {
    "Inicio":                   "views.inicio",
    "Flujo Guiado":             "views.flujo",
    "Buscador":                 "views.buscador",
    "Cotización":               "views.cotizacion",
    "Historial Cotizaciones":   "views.historial_cotizaciones",
    "Ventas":                   "views.ventas",
    "Facturación":              "views.facturacion",
    "Inventario":               "views.inventario",
    "Herramientas":             "views.herramientas",
    "Insumos":                  "views.insumos",
    "Kits":                     "views.kits",
    "Proveedores":              "views.proveedores",
    "Proyectos":                "views.proyectos",
    "OT":                       "views.ot",
    "Garantías":                "views.garantias",
    "Clientes":                 "views.clientes",
    "Vendedores":               "views.vendedores",
    "Respaldo y Restauración":  "views.respaldo",
    "Administración":           "views.admin",
}

if current_tab in _views:
    import importlib
    mod = importlib.import_module(_views[current_tab])
    mod.render()
