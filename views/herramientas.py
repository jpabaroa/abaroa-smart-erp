import streamlit as st
from database import (get_df, get_conn, normalize_tools_df, calc_monthly_tool_cost, import_tools_csv)
from utils import money

def render():
    st.subheader("Herramientas y Activos")
    st.caption("Activos de trabajo separados del inventario vendible.")
    tools_df = normalize_tools_df(get_df("SELECT * FROM tools_assets ORDER BY tool_name, asset_id"))
    tool_search = st.text_input("Buscar herramienta", placeholder="Asset ID, nombre, proveedor...")
    if str(tool_search).strip() and not tools_df.empty:
        n = tool_search.strip().lower()
        tools_df = tools_df[tools_df["asset_id"].astype(str).str.lower().str.contains(n,na=False)
                           | tools_df["tool_name"].astype(str).str.lower().str.contains(n,na=False)
                           | tools_df["provider"].astype(str).str.lower().str.contains(n,na=False)
                           | tools_df["status"].astype(str).str.lower().str.contains(n,na=False)].copy()
    total_inv = int((tools_df["cost_unit"] * tools_df["quantity"]).sum()) if not tools_df.empty else 0
    total_monthly = int(tools_df["monthly_cost"].sum()) if not tools_df.empty else 0
    c1,c2,c3 = st.columns(3)
    c1.metric("Herramientas", len(tools_df))
    c2.metric("Inversión total", money(total_inv))
    c3.metric("Costo mensual est.", money(total_monthly))

    with st.expander("Importar CSV", expanded=False):
        up = st.file_uploader("CSV herramientas", type=["csv"])
        if st.button("Importar") and up:
            try:
                n_inserted = import_tools_csv(up)
                st.success(f"{n_inserted} herramientas importadas.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown("### Registrar / editar herramienta")
    tool_opts = ["Nueva"] + (tools_df["asset_id"].astype(str).tolist() if not tools_df.empty else [])
    sel = st.selectbox("Herramienta", tool_opts)
    cur = tools_df[tools_df["asset_id"].astype(str)==sel].iloc[0].to_dict() if sel!="Nueva" and not tools_df.empty else {}
    with st.form("tool_form"):
        t1,t2,t3,t4 = st.columns(4)
        asset_id = t1.text_input("Asset ID *", value=str(cur.get("asset_id","")))
        tool_name = t2.text_input("Nombre *", value=str(cur.get("tool_name","")))
        provider = t3.text_input("Proveedor", value=str(cur.get("provider","") or ""))
        status = t4.selectbox("Estado", ["Activa","En mantención","Baja"],
                               index=(["Activa","En mantención","Baja"].index(str(cur.get("status","Activa")))
                                      if str(cur.get("status","Activa")) in ["Activa","En mantención","Baja"] else 0))
        t5,t6,t7,t8 = st.columns(4)
        category = t5.text_input("Categoría", value=str(cur.get("category","Herramienta") or "Herramienta"))
        quantity = int(t6.number_input("Cantidad", min_value=1, value=int(cur.get("quantity",1) or 1), step=1))
        cost_unit = int(t7.number_input("Costo unitario", min_value=0, value=int(cur.get("cost_unit",0) or 0), step=100))
        useful_life = int(t8.number_input("Vida útil (meses)", min_value=1, value=int(cur.get("useful_life_months",12) or 12), step=1))
        t9,t10 = st.columns(2)
        purchase_date = t9.text_input("Fecha compra", value=str(cur.get("purchase_date","") or ""), placeholder="YYYY-MM-DD")
        notes = t10.text_input("Notas", value=str(cur.get("notes","") or ""))
        monthly = calc_monthly_tool_cost(cost_unit, quantity, useful_life)
        st.info(f"Costo mensual estimado: {money(monthly)}")
        s1,s2,s3 = st.columns(3)
        save_tool = s1.form_submit_button("Guardar", type="primary")
        del_tool = s2.form_submit_button("Eliminar")
        _ = s3.form_submit_button("Limpiar")
    if save_tool:
        if not str(asset_id).strip() or not str(tool_name).strip():
            st.error("Asset ID y Nombre son obligatorios.")
        else:
            conn = get_conn()
            conn.execute("""
                INSERT INTO tools_assets (asset_id,tool_name,category,provider,quantity,cost_unit,
                    purchase_date,useful_life_months,monthly_cost,status,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(asset_id) DO UPDATE SET tool_name=excluded.tool_name, category=excluded.category,
                    provider=excluded.provider, quantity=excluded.quantity, cost_unit=excluded.cost_unit,
                    purchase_date=excluded.purchase_date, useful_life_months=excluded.useful_life_months,
                    monthly_cost=excluded.monthly_cost, status=excluded.status, notes=excluded.notes
            """, (str(asset_id).strip(), str(tool_name).strip(), str(category).strip() or "Herramienta",
                  str(provider).strip(), int(quantity), int(cost_unit), str(purchase_date).strip(),
                  int(useful_life), int(monthly), str(status).strip(), str(notes).strip()))
            conn.commit()
            conn.close()
            st.success("Herramienta guardada.")
            st.rerun()
    if del_tool and sel!="Nueva":
        conn = get_conn()
        conn.execute("DELETE FROM tools_assets WHERE asset_id=?", (sel,))
        conn.commit()
        conn.close()
        st.success("Herramienta eliminada.")
        st.rerun()

    st.markdown("### Listado")
    if tools_df.empty:
        st.info("Sin herramientas registradas.")
    else:
        display = tools_df.copy()
        display["inversion_total"] = display["cost_unit"].astype(int) * display["quantity"].astype(int)
        st.dataframe(display[["asset_id","tool_name","category","provider","quantity","cost_unit","monthly_cost","inversion_total","status","purchase_date","notes"]],
                     use_container_width=True, hide_index=True)
