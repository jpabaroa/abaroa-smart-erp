import streamlit as st
from database import run_global_search
from utils import money
import pandas as pd

def render():
    st.subheader("Buscador global")
    q1, q2 = st.columns([3,1])
    term = q1.text_input("Buscar en toda la base", value=st.session_state.get("global_search",""), placeholder="SKU, cliente, OT, proyecto...")
    only_hits = q2.checkbox("Solo módulos con resultados", value=True)
    if not str(term).strip():
        st.info("Escribe un término para buscar.")
        return
    results = run_global_search(term)
    total_hits = sum(len(df) for df in results.values())
    st.metric("Coincidencias totales", total_hits)
    for module_name in ["Inventario","Clientes","Cotizaciones","OT","Proyectos","Ventas","Kits","Proveedores"]:
        df = results.get(module_name, pd.DataFrame())
        if only_hits and df.empty:
            continue
        st.markdown(f"### {module_name}")
        if df.empty:
            st.caption("Sin resultados.")
        else:
            view = df.copy()
            if "monto" in view.columns:
                view["monto"] = view["monto"].apply(lambda x: money(x) if pd.notna(x) and str(x)!='' else "")
            view.columns = ["Código","Título","Detalle 1","Detalle 2","Monto"]
            st.dataframe(view, use_container_width=True, hide_index=True)
