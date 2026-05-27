import streamlit as st
from database import (get_df, get_conn, q, recalc_stock, recalc_all_sale_prices,
                      calc_sale_price, next_sku_for_category, save_inventory_image,
                      inventory_image_web_path)
from utils import money


def reset_editor():
    st.session_state["inv_selected"] = "Nuevo"
    st.session_state["inv_form_v"] = st.session_state.get("inv_form_v", 0) + 1
    st.session_state["inv_img_key"] = st.session_state.get("inv_img_key", 0) + 1


def render():
    st.subheader("Inventario")

    for k, v in [("inv_selected","Nuevo"),("inv_form_v",0),("inv_img_key",0)]:
        if k not in st.session_state:
            st.session_state[k] = v

    inv_df = get_df("SELECT * FROM inventory ORDER BY category, sku")
    for col in ["image_path","location"]:
        if col not in inv_df.columns:
            inv_df[col] = ""

    # Búsqueda rápida
    sl, sr = st.columns([2,1])
    find = sl.text_input("Buscar por SKU o descripción", placeholder="Ej: PRD-SEN-0001 o sensor")
    if sr.button("Ir al primero", use_container_width=True):
        if str(find).strip() and not inv_df.empty:
            needle = find.strip().lower()
            matches = inv_df[
                inv_df["sku"].str.lower().str.contains(needle, na=False)
                | inv_df["description"].str.lower().str.contains(needle, na=False)
            ]
            if not matches.empty:
                st.session_state["inv_selected"] = str(matches.iloc[0]["sku"])
                st.session_state["inv_form_v"] = st.session_state.get("inv_form_v", 0) + 1
                st.rerun()
            else:
                st.warning(f"Sin resultados para '{find.strip()}'.")

    # Selector — opciones con SKU + descripción para facilitar identificación
    sku_list = inv_df["sku"].tolist()
    desc_map = dict(zip(inv_df["sku"], inv_df["description"].fillna(""))) if not inv_df.empty else {}
    display_opts = ["Nuevo"] + [
        f"{sku}  —  {desc_map.get(sku,'')}" if desc_map.get(sku,"") else sku
        for sku in sku_list
    ]
    sku_opts = ["Nuevo"] + sku_list

    pending = st.session_state.pop("inv_selected", None)
    if pending is not None and pending in sku_opts:
        default_idx = sku_opts.index(pending)
    else:
        default_idx = 0

    sel_display = st.selectbox(
        "Seleccionar ítem",
        display_opts,
        index=default_idx,
        key=f"inv_sel_{st.session_state.get('inv_form_v', 0)}"
    )
    # Recuperar SKU limpio desde la opción mostrada
    selected = sku_opts[display_opts.index(sel_display)]
    current = inv_df[inv_df["sku"] == selected].iloc[0].to_dict() if selected != "Nuevo" and not inv_df.empty and selected in inv_df["sku"].values else {}

    # Edición rápida inline
    if selected != "Nuevo" and current:
        with st.expander("⚡ Edición rápida (sin formulario completo)", expanded=False):
            qc1, qc2, qc3, qc4, qc5, qc6 = st.columns(6)
            q_desc = qc1.text_input("Descripción", value=str(current.get("description","")), key=f"qd_{selected}")
            q_cost = qc2.number_input("Costo unit.", min_value=0, value=int(current.get("cost_unit",0) or 0), step=100, key=f"qc_{selected}")
            q_margin = qc3.number_input("Margen %", min_value=0, max_value=100, value=int(current.get("margin_pct",0) or 0), key=f"qm_{selected}")
            q_stock_min = qc4.number_input("Stock mínimo", min_value=0, value=int(current.get("stock_min",0) or 0), key=f"qsm_{selected}")
            q_provider = qc5.text_input("Proveedor", value=str(current.get("provider","") or ""), key=f"qp_{selected}")
            suggested = calc_sale_price(q_cost, q_margin) if q_cost else 0
            qc6.metric("Precio sugerido", money(suggested))
            if st.button("💾 Guardar edición rápida", key=f"q_save_{selected}"):
                conn = get_conn()
                conn.execute("UPDATE inventory SET description=?,cost_unit=?,margin_pct=?,sale_price=?,provider=?,stock_min=? WHERE sku=?",
                             (q_desc.strip(), int(q_cost), int(q_margin), int(suggested), q_provider.strip(), int(q_stock_min), selected))
                if q_provider.strip():
                    conn.execute("INSERT OR IGNORE INTO suppliers (name) VALUES (?)", (q_provider.strip(),))
                conn.commit()
                conn.close()
                recalc_stock()
                st.success(f"Cambios guardados para {selected}.")
                st.rerun()

    # Vista previa imagen
    if selected != "Nuevo" and current:
        current_image = inventory_image_web_path(current.get("image_path",""))
        prev_col, data_col = st.columns([1,2])
        with prev_col:
            if current_image:
                st.image(current_image, caption=f"Foto · {selected}", use_container_width=True)
            else:
                st.caption("Sin foto cargada")
        with data_col:
            st.markdown(f"**SKU:** {selected}")
            st.markdown(f"**Ubicación:** {current.get('location','') or 'Sin definir'}")
            st.markdown(f"**Proveedor:** {current.get('provider','') or 'Sin proveedor'}")

    # Formulario completo
    fv = st.session_state.get("inv_form_v", 0)
    existing_cats = sorted([c for c in inv_df["category"].dropna().astype(str).unique().tolist() if c]) if not inv_df.empty else []
    cat_opts = existing_cats + (["Otra..."] if "Otra..." not in existing_cats else [])
    current_cat = str(current.get("category","")) if current else ""
    default_cat = current_cat if current_cat in existing_cats else ("Otra..." if current_cat else (existing_cats[0] if existing_cats else "Otra..."))
    existing_skus = inv_df["sku"].tolist() if not inv_df.empty else []

    with st.form(f"inv_form_{fv}"):
        a, b, c2, d = st.columns(4)
        description = a.text_input("Descripción", value=str(current.get("description","")) , key=f"inv_desc_{fv}")
        cat_choice = b.selectbox("Categoría", cat_opts if cat_opts else ["Otra..."],
                                  index=(cat_opts.index(default_cat) if default_cat in cat_opts else 0), key=f"inv_cat_{fv}")
        cat_custom = c2.text_input("Nueva categoría", value=(current_cat if default_cat=="Otra..." else ""), key=f"inv_cat_new_{fv}")
        protocols = ["Zigbee","Wi-Fi","Configuración","Servicios","Auditoria","Otro..."]
        cur_prot = str(current.get("protocol","") or "")
        prot_choice = d.selectbox("Protocolo", protocols,
                                   index=(protocols.index(cur_prot) if cur_prot in protocols else (protocols.index("Otro...") if cur_prot else 0)), key=f"inv_prot_{fv}")
        prot_custom = st.text_input("Otro protocolo", value=(cur_prot if cur_prot and cur_prot not in protocols[:-1] else ""), key=f"inv_prot_new_{fv}")
        category = cat_custom.strip() if cat_choice=="Otra..." else cat_choice
        protocol = prot_custom.strip() if prot_choice=="Otro..." else prot_choice
        is_service = st.checkbox("Es servicio", value=bool(current.get("is_service",0)), key=f"inv_srv_{fv}")
        auto_sku = current.get("sku","") if selected!="Nuevo" else next_sku_for_category(category or "General", existing_skus, is_service)
        e, f2, g, h, i, j = st.columns(6)
        e.text_input("SKU", value=str(auto_sku), disabled=True, key=f"inv_sku_{fv}")
        stock_initial = f2.number_input("Stock inicial", min_value=0, value=int(current.get("stock_initial",0) or 0), step=1, key=f"inv_si_{fv}")
        stock_min = g.number_input("Stock mínimo", min_value=0, value=int(current.get("stock_min",0) or 0), step=1, key=f"inv_smin_{fv}")
        cost_unit = h.number_input("Costo unitario", min_value=0, value=int(current.get("cost_unit",0) or 0), step=100, key=f"inv_cost_{fv}")
        margin_pct = i.number_input("Margen %", min_value=0, max_value=100, value=int(current.get("margin_pct",0) or 0), step=1, key=f"inv_margin_{fv}")
        provider = j.text_input("Proveedor", value=str(current.get("provider","") or ""), key=f"inv_prov_{fv}")
        l1, l2 = st.columns(2)
        location = l1.text_input("Ubicación en bodega", value=str(current.get("location","") or ""), key=f"inv_loc_{fv}")
        image_file = l2.file_uploader("Foto del producto", type=["png","jpg","jpeg","webp"], key=f"inv_img_{st.session_state.get('inv_img_key',0)}")
        sale_price_preview = calc_sale_price(cost_unit, margin_pct) if cost_unit else 0
        st.info(f"SKU auto: {auto_sku} | Precio sugerido: {money(sale_price_preview)}")
        recalc_btn = st.form_submit_button("Recalcular todos los precios")
        if recalc_btn:
            recalc_all_sale_prices()
            st.success("Precios recalculados.")
        s1, s2, s3 = st.columns(3)
        save_btn = s1.form_submit_button("💾 Guardar nuevo")
        edit_btn = s2.form_submit_button("✏️ Editar")
        delete_btn = s3.form_submit_button("🗑️ Eliminar")
        if save_btn or edit_btn:
            if save_btn and selected != "Nuevo":
                st.error("Para crear, selecciona 'Nuevo' en el selector.")
            elif edit_btn and selected == "Nuevo":
                st.error("Selecciona un ítem existente para editar.")
            elif not description or not category or not protocol:
                st.error("Descripción, categoría y protocolo son obligatorios.")
            else:
                sale_price = calc_sale_price(cost_unit, margin_pct) if cost_unit else 0
                final_sku = current.get("sku","") if selected!="Nuevo" else auto_sku
                image_path = current.get("image_path","") or ""
                if image_file is not None:
                    image_path = save_inventory_image(image_file, final_sku)
                conn = get_conn()
                existing_row = conn.execute("SELECT sku, stock_current, stock_reserved FROM inventory WHERE sku=?", (final_sku,)).fetchone()
                if save_btn and existing_row:
                    conn.close()
                    st.error(f"Ya existe un ítem con SKU {final_sku}.")
                else:
                    if provider.strip():
                        conn.execute("INSERT OR IGNORE INTO suppliers (name) VALUES (?)", (provider.strip(),))
                    if save_btn:
                        stock_current = 0 if is_service else int(stock_initial)
                        conn.execute("""INSERT INTO inventory (sku,description,category,protocol,stock_initial,stock_current,
                            cost_unit,margin_pct,sale_price,provider,is_service,stock_min,image_path,location)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (final_sku, description, category, protocol, int(stock_initial), int(stock_current),
                             int(cost_unit), int(margin_pct), int(sale_price), provider, 1 if is_service else 0, int(stock_min), image_path, location.strip()))
                    else:
                        cur_stock = int(current.get("stock_current",0) or 0)
                        cur_reserved = int(current.get("stock_reserved",0) or 0)
                        if is_service:
                            new_stock = 0
                        else:
                            delta = int(stock_initial) - int(current.get("stock_initial",0) or 0)
                            new_stock = max(cur_stock + delta, cur_reserved, 0)
                        conn.execute("""UPDATE inventory SET description=?,category=?,protocol=?,stock_initial=?,stock_current=?,
                            cost_unit=?,margin_pct=?,sale_price=?,provider=?,is_service=?,stock_min=?,image_path=?,location=?
                            WHERE sku=?""",
                            (description, category, protocol, int(stock_initial), int(new_stock), int(cost_unit),
                             int(margin_pct), int(sale_price), provider, 1 if is_service else 0, int(stock_min), image_path, location.strip(), final_sku))
                    conn.commit()
                    conn.close()
                    recalc_stock()
                    reset_editor()
                    st.success(f"Ítem {'creado' if save_btn else 'editado'}: {final_sku}.")
                    st.rerun()
        if delete_btn and selected != "Nuevo":
            conn = get_conn()
            conn.execute("DELETE FROM inventory WHERE sku=?", (selected,))
            conn.commit()
            conn.close()
            reset_editor()
            st.success("Ítem eliminado.")
            st.rerun()

    # Tabla completa
    st.markdown("### Vista tabular del inventario")
    inv_table = get_df("""
        SELECT i.category, i.sku, i.description, i.protocol, i.location, i.stock_initial,
               i.stock_current, COALESCE(i.stock_reserved,0) AS stock_reserved,
               i.stock_min, i.cost_unit, i.margin_pct, i.sale_price, i.provider, i.is_service,
               COALESCE(SUM(v.sold_qty),0) AS sold_qty, COALESCE(u.used_qty,0) AS used_qty
        FROM inventory i
        LEFT JOIN (
            SELECT qi.sku, SUM(qi.quantity) AS sold_qty FROM quote_items qi
            JOIN quotes q ON q.id=qi.quote_id
            WHERE qi.item_type='producto' AND q.status IN ('Aprobada','Aceptada','Vendida','Facturada')
            GROUP BY qi.sku
        ) v ON v.sku=i.sku
        LEFT JOIN (
            SELECT sku, SUM(used_quantity) AS used_qty FROM project_items
            WHERE item_type IN ('producto','kit_component') GROUP BY sku
        ) u ON u.sku=i.sku
        GROUP BY i.category,i.sku,i.description,i.protocol,i.location,i.stock_initial,
                 i.stock_current,i.stock_reserved,i.stock_min,i.cost_unit,i.margin_pct,
                 i.sale_price,i.provider,i.is_service,u.used_qty
        ORDER BY i.category, i.sku
    """)
    if not inv_table.empty:
        for col in ["stock_current","stock_reserved","sold_qty","used_qty"]:
            inv_table[col] = inv_table[col].fillna(0).astype(int)
        inv_table["disponible"] = inv_table["stock_current"] - inv_table["stock_reserved"]
    st.dataframe(inv_table, use_container_width=True, hide_index=True, column_config={
        "category": st.column_config.TextColumn("Categoría"),
        "sku": st.column_config.TextColumn("SKU"),
        "description": st.column_config.TextColumn("Descripción"),
        "protocol": st.column_config.TextColumn("Protocolo"),
        "location": st.column_config.TextColumn("Ubicación"),
        "stock_initial": st.column_config.NumberColumn("Stock inicial", format="%d"),
        "stock_current": st.column_config.NumberColumn("Stock actual", format="%d"),
        "stock_reserved": st.column_config.NumberColumn("Reservado", format="%d"),
        "stock_min": st.column_config.NumberColumn("Mínimo", format="%d"),
        "disponible": st.column_config.NumberColumn("Disponible", format="%d"),
        "cost_unit": st.column_config.NumberColumn("Costo", format="$ %d"),
        "margin_pct": st.column_config.NumberColumn("Margen %", format="%d%%"),
        "sale_price": st.column_config.NumberColumn("Precio venta", format="$ %d"),
        "provider": st.column_config.TextColumn("Proveedor"),
        "is_service": st.column_config.CheckboxColumn("Servicio"),
        "sold_qty": st.column_config.NumberColumn("Vendido", format="%d"),
        "used_qty": st.column_config.NumberColumn("Usado", format="%d"),
    })

    # Catálogo visual
    st.markdown("### Catálogo visual de bodega")
    catalog_df = get_df("SELECT sku,description,category,protocol,location,stock_current,stock_min,sale_price,image_path FROM inventory WHERE is_service=0 ORDER BY category,description")
    if catalog_df.empty:
        st.info("Aún no hay productos cargados.")
        return
    sc, cc = st.columns([2,1])
    search_text = sc.text_input("Buscar producto", value="")
    categories_catalog = ["Todas"] + sorted([c for c in catalog_df["category"].dropna().unique().tolist() if c])
    selected_cat = cc.selectbox("Filtrar categoría", categories_catalog)
    filtered = catalog_df.copy()
    if search_text.strip():
        n = search_text.strip().lower()
        filtered = filtered[filtered["sku"].str.lower().str.contains(n,na=False)
                          | filtered["description"].str.lower().str.contains(n,na=False)
                          | filtered["location"].str.lower().str.contains(n,na=False)]
    if selected_cat != "Todas":
        filtered = filtered[filtered["category"] == selected_cat]
    cols = st.columns(3)
    for idx, row in filtered.reset_index(drop=True).iterrows():
        with cols[idx % 3]:
            with st.container(border=True):
                img = inventory_image_web_path(row.get("image_path",""))
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.caption("Sin foto")
                st.markdown(f"**{row['description']}**")
                st.caption(f"SKU: {row['sku']} · {row['category']}")
                st.write(f"Protocolo: {row['protocol'] or '-'}")
                st.write(f"Ubicación: {row['location'] or 'Sin definir'}")
                st.write(f"Stock: {int(row['stock_current'] or 0)} / mín {int(row['stock_min'] or 0)}")
                st.write(f"Precio: {money(row['sale_price'] or 0)}")
