"""
app.py — Abaroa Smart ERP
Entry point: configuración, tema premium, sidebar y despachador de vistas.

CORRECCIONES v3:
  - Se abandonó el control custom del sidebar via CSS inyectado (perdía la
    guerra de especificidad contra el CSS interno de Streamlit en mobile).
    Ahora se usa el comportamiento nativo + initial_sidebar_state dinámico.
  - render_header: eliminado parámetro value= en st.text_input que causaba
    StreamlitAPIException cuando global_search ya existía en session_state
"""

import streamlit as st
from utils import apply_theme, logo
from database import (
    init_db, migrate_db, ensure_app_settings, recalc_all_sale_prices, recalc_stock,
    remove_duplicate_rows, get_alerts_data, admin_logged_in,
    verify_admin_credentials, get_setting,
)

# ── Config ────────────────────────────────────────────────────────────────────
_already_logged_in = st.session_state.get("admin_logged_in", False)
st.set_page_config(
    page_title="Abaroa Smart ERP",
    layout="wide",
    page_icon="💡",
    initial_sidebar_state="expanded" if _already_logged_in else "collapsed",
)
apply_theme()
init_db()
migrate_db()
ensure_app_settings()
remove_duplicate_rows()
recalc_all_sale_prices()
recalc_stock()

# ── Session state ─────────────────────────────────────────────────────────────
if "current_tab"     not in st.session_state: st.session_state["current_tab"]     = "Inicio"
if "global_search"   not in st.session_state: st.session_state["global_search"]   = ""
if "admin_logged_in" not in st.session_state: st.session_state["admin_logged_in"] = False

# ── CSS sidebar open/close ────────────────────────────────────────────────────
# FIX: usar components.html() con JS → window.parent.document, NO
# st.markdown(unsafe_allow_html=True): ese método filtra/elimina las etiquetas
# <style> en Streamlit ≥1.38, lo que dejaba el sidebar nativo (vacío, expandido)
# tapando la pantalla de login en mobile y sin botón para colapsarlo.

# ── Sidebar: se usa el comportamiento NATIVO de Streamlit ────────────────────
# Después de 3 rondas peleando con CSS inyectado vía JS contra los estilos
# internos de Streamlit (que se reaplican en cada render y ganan la guerra de
# especificidad), se abandona el control custom del sidebar. Streamlit ya trae
# su propia flecha para abrir/cerrar el sidebar — es la única vía confiable
# en mobile. `initial_sidebar_state` solo gobierna la primera carga.
# ── Login obligatorio ─────────────────────────────────────────────────────────
def render_login_screen():
    """Pantalla de login de pantalla completa. Bloquea el acceso a todo el ERP
    hasta que se ingresen credenciales válidas. initial_sidebar_state="collapsed"
    (ver arriba) ya se encarga de que el sidebar no aparezca aquí."""
    logo(width=180)
    st.markdown(
        "<div style='text-align:center; opacity:.7; margin:0.5rem 0 1.5rem;'>"
        "Ingresa tus credenciales para continuar</div>",
        unsafe_allow_html=True,
    )
    with st.form("login_form"):
        lu = st.text_input("Usuario")
        lp = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar", use_container_width=True, type="primary")
        if submitted:
            if verify_admin_credentials(lu, lp):
                st.session_state["admin_logged_in"] = True
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")


if not admin_logged_in():
    render_login_screen()
    st.stop()


# ── HEADER ────────────────────────────────────────────────────────────────────
def render_header():
    current_tab = st.session_state["current_tab"]
    h1, h2, h3, h4, h5 = st.columns([0.5, 3.2, 6, 0.65, 0.65])

    with h1:
        st.markdown(
            "<div style='opacity:.5; font-size:.75rem; padding-top:.6rem;'>☰ menú</div>",
            unsafe_allow_html=True,
        )

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
            st.success(f"**{get_setting('admin_username','admin')}**")
            if st.button("Panel admin", key="hdr_admin_go"):
                st.session_state["current_tab"] = "Administración"
                st.rerun()
            if st.button("Cerrar sesión", key="hdr_logout"):
                st.session_state["admin_logged_in"] = False
                st.rerun()

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
    nav = {
        "Principal":  [("Inicio","🏠 Inicio"), ("Flujo Guiado","🧭 Flujo Guiado"), ("Buscador","🔎 Buscador")],
        "Operación":  [("Proyectos","🛠️ Proyectos"), ("OT","📋 OT"), ("Garantías","🛡️ Garantías")],
        "Comercial":  [("Levantamiento","🔍 Levantamiento"), ("Cotización","🧾 Cotización"), ("Historial Cotizaciones","📚 Historial"),
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
    "Levantamiento":            "views.levantamiento",
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
