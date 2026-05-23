from datetime import date, datetime
import streamlit as st
from database import get_df

def render():
    st.subheader("Garantías")
    df = get_df("""
        SELECT w.id, c.name AS cliente, w.install_date, w.warranty_months, w.expiry_date, w.status, w.notes, w.sale_id
        FROM warranties w LEFT JOIN clients c ON c.id=w.client_id ORDER BY w.id DESC
    """)
    if df.empty:
        st.info("No hay garantías registradas.")
        return
    today = date.today()
    def calc_status(expiry):
        try:
            exp = datetime.fromisoformat(str(expiry)).date()
            if exp < today: return "🔴 Vencida"
            elif (exp - today).days <= 30: return "🟡 Por vencer"
            return "🟢 Vigente"
        except Exception:
            return "Sin fecha"
    df["Estado actual"] = df["expiry_date"].apply(calc_status)
    vencidas = int((df["Estado actual"] == "🔴 Vencida").sum())
    por_vencer = int((df["Estado actual"] == "🟡 Por vencer").sum())
    vigentes = int((df["Estado actual"] == "🟢 Vigente").sum())
    c1,c2,c3 = st.columns(3)
    c1.metric("Vigentes", vigentes)
    c2.metric("Por vencer (30 días)", por_vencer)
    c3.metric("Vencidas", vencidas)
    st.dataframe(df[["id","cliente","sale_id","install_date","expiry_date","Estado actual","warranty_months","notes"]],
                 use_container_width=True, hide_index=True)
