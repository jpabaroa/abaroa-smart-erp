import streamlit as st
from database import (
    get_df, get_conn, q, create_survey, update_survey_header, add_survey_item,
    delete_survey_item, get_survey_items_df, get_surveys_df, get_survey,
    save_survey_photo, survey_photo_web_path, build_quote_lines_from_survey,
)
from utils import money


def render():
    st.subheader("🔍 Levantamiento en Terreno")
    st.caption("Registra cámaras, interruptores, cajas de registro y cualquier ítem detectado en la visita técnica.")

    if "survey_id" not in st.session_state:
        st.session_state["survey_id"] = None
    if "survey_photo_key" not in st.session_state:
        st.session_state["survey_photo_key"] = 0

    clients_df = get_df("SELECT * FROM clients ORDER BY name")
    if clients_df.empty:
        st.warning("Primero crea al menos un cliente en el módulo **Clientes**.")
        return

    # ── Selector de levantamiento existente / nuevo ─────────────────────────
    surveys_df = get_surveys_df()
    with st.expander("📂 Levantamientos existentes", expanded=(st.session_state["survey_id"] is None)):
        if not surveys_df.empty:
            opts = [f'{int(r["id"])} · {r["client_name"]} · {r["survey_date"]} · {r["status"]}'
                    for _, r in surveys_df.iterrows()]
            sel = st.selectbox("Abrir levantamiento existente", [""] + opts, key="survey_picker")
            if sel and st.button("Abrir"):
                st.session_state["survey_id"] = int(sel.split(" · ")[0])
                st.rerun()
        else:
            st.caption("Aún no hay levantamientos registrados.")

    if st.session_state["survey_id"] is None:
        st.markdown("### Nuevo levantamiento")
        client_opts = [f'{int(r["id"])} · {r["name"]}' for _, r in clients_df.iterrows()]
        wf_client = st.session_state.get("workflow_client_id")
        default_idx = 0
        if wf_client:
            for i, o in enumerate(client_opts):
                if o.startswith(f"{wf_client} · "):
                    default_idx = i
                    break
        n1, n2 = st.columns(2)
        sel_client = n1.selectbox("Cliente", client_opts, index=default_idx)
        client_id = int(sel_client.split(" · ")[0])
        technician = n2.text_input("Técnico / responsable de la visita")
        address = st.text_input("Dirección de la visita")
        if st.button("Crear levantamiento", type="primary"):
            sid = create_survey(client_id, address=address, technician=technician)
            st.session_state["survey_id"] = sid
            st.success("Levantamiento creado.")
            st.rerun()
        return

    # ── Levantamiento activo ────────────────────────────────────────────────
    survey = get_survey(st.session_state["survey_id"])
    if not survey:
        st.session_state["survey_id"] = None
        st.rerun()
        return

    hc1, hc2, hc3 = st.columns([3, 1, 1])
    hc1.markdown(f"### Levantamiento #{survey['id']} · {survey['client_name']}")
    hc2.write(f"Estado: **{survey['status']}**")
    if hc3.button("← Cambiar levantamiento"):
        st.session_state["survey_id"] = None
        st.rerun()

    with st.expander("Datos generales de la visita", expanded=False):
        with st.form("survey_header_form"):
            address = st.text_input("Dirección", value=str(survey.get("address", "") or ""))
            technician = st.text_input("Técnico", value=str(survey.get("technician", "") or ""))
            gen_notes = st.text_area("Notas generales", value=str(survey.get("general_notes", "") or ""))
            if st.form_submit_button("Guardar datos generales"):
                update_survey_header(survey["id"], address=address, technician=technician, notes=gen_notes)
                st.success("Datos guardados.")
                st.rerun()

    # ── Agregar ítem ─────────────────────────────────────────────────────────
    st.markdown("### Agregar ítem")

    inv_df = get_df("SELECT sku, description, sale_price, is_service FROM inventory ORDER BY description")
    supplies_df = get_df("SELECT description, default_unit_price FROM supplies_catalog ORDER BY description")

    catalog_opts = ["Nueva categoría..."]
    catalog_opts += [f'{r["sku"]} · {r["description"]}' for _, r in inv_df.iterrows()]
    catalog_opts += [f'INSUMO · {r["description"]}' for _, r in supplies_df.iterrows()]

    i1, i2 = st.columns([3, 2])
    cat_choice = i1.selectbox("Categoría / ítem del catálogo", catalog_opts, key="survey_item_cat")
    sku = ""
    default_price = 0
    custom_cat = ""
    if cat_choice == "Nueva categoría...":
        custom_cat = i2.text_input("Nombre de la categoría nueva", key="survey_item_custom",
                                    placeholder="Ej: Caja de registro exterior")
    else:
        sku_part, desc_part = cat_choice.split(" · ", 1)
        if sku_part != "INSUMO":
            sku = sku_part
            row = inv_df[inv_df["sku"] == sku]
            if not row.empty:
                default_price = int(row.iloc[0]["sale_price"] or 0)
        else:
            row = supplies_df[supplies_df["description"] == desc_part]
            if not row.empty:
                default_price = int(row.iloc[0]["default_unit_price"] or 0)

    j1, j2, j3 = st.columns(3)
    qty = j1.number_input("Cantidad", min_value=1, value=1, step=1, key="survey_item_qty")
    zone = j2.text_input("Zona / ubicación", key="survey_item_zone", placeholder="Ej: Living, 2do piso")
    price = j3.number_input("Precio estimado", min_value=0, value=default_price, step=100, key="survey_item_price")

    tech_notes = st.text_area(
        "Notas técnicas", key="survey_item_notes",
        placeholder="Ej: altura de instalación, marca preferida, distancia de cableado...",
    )
    photo = st.file_uploader(
        "Foto del lugar / ítem", type=["png", "jpg", "jpeg", "webp"],
        key=f"survey_item_photo_{st.session_state['survey_photo_key']}",
    )

    if st.button("➕ Agregar ítem al levantamiento", type="primary"):
        category = custom_cat.strip() if cat_choice == "Nueva categoría..." else cat_choice.split(" · ", 1)[1]
        if not category:
            st.error("Indica una categoría o selecciona un ítem del catálogo.")
        else:
            item_id = add_survey_item(
                survey["id"], category=category, sku=sku, item_type="producto",
                quantity=qty, zone=zone, technical_notes=tech_notes, unit_price=price,
            )
            if photo is not None:
                photo_path = save_survey_photo(photo, survey["id"], item_id)
                conn = get_conn()
                q(conn, "UPDATE site_survey_items SET photo_path=? WHERE id=?", (photo_path, item_id))
                conn.close()
            st.session_state["survey_photo_key"] += 1
            st.success("Ítem agregado.")
            st.rerun()

    # ── Lista de ítems ───────────────────────────────────────────────────────
    st.markdown("### Ítems registrados")
    items_df = get_survey_items_df(survey["id"])
    if items_df.empty:
        st.info("Aún no hay ítems en este levantamiento.")
    else:
        for _, it in items_df.iterrows():
            with st.container(border=True):
                cc1, cc2 = st.columns([1, 4])
                with cc1:
                    photo_path = survey_photo_web_path(it.get("photo_path", ""))
                    if photo_path:
                        st.image(photo_path, use_container_width=True)
                    else:
                        st.caption("Sin foto")
                with cc2:
                    st.markdown(f"**{it['category']}** · x{int(it['quantity'])} · {it.get('zone', '') or 'Sin zona'}")
                    if it.get("sku"):
                        st.caption(f"SKU: {it['sku']} · Precio: {money(it.get('unit_price', 0))}")
                    else:
                        st.caption(f"Sin SKU (ítem manual) · Precio estimado: {money(it.get('unit_price', 0))}")
                    if it.get("technical_notes"):
                        st.caption(f"📝 {it['technical_notes']}")
                    if st.button("🗑 Eliminar ítem", key=f"del_survey_item_{it['id']}"):
                        delete_survey_item(int(it["id"]))
                        st.rerun()

    # ── Acciones finales ─────────────────────────────────────────────────────
    if not items_df.empty:
        st.markdown("---")
        st.markdown("### Generar cotización desde este levantamiento")
        st.caption(
            "Los ítems con SKU real tomarán el precio vigente del catálogo. "
            "Los ítems sin SKU (categorías nuevas) pasan como insumo con el precio estimado que ingresaste."
        )
        if st.button("🧾 Crear cotización desde levantamiento", type="primary", use_container_width=True):
            product_lines, service_lines, supply_lines = build_quote_lines_from_survey(survey["id"])
            st.session_state["quote_products"] = product_lines
            st.session_state["quote_services"] = service_lines
            st.session_state["quote_supplies"] = supply_lines
            st.session_state["quote_kits"] = st.session_state.get("quote_kits", [])
            st.session_state["prefill_quote_client_id"] = survey["client_id"]
            st.session_state["pending_survey_link"] = survey["id"]
            st.session_state["current_tab"] = "Cotización"
            st.success("Ítems trasladados a Cotización. Revisa y guarda para confirmar.")
            st.rerun()
