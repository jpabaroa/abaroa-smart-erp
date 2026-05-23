import streamlit as st
from database import get_conn, get_df, get_dashboard_work_orders_df
from utils import money, dashboard_kpi_card, section_header


def render():
    conn = get_conn()

    # ── Datos KPIs ──────────────────────────────────────────────────────────
    row = conn.execute(
        "SELECT COALESCE(SUM(total),0) AS t, COALESCE(SUM(material_cost),0) AS c, "
        "COALESCE(SUM(gross_margin),0) AS m, COALESCE(AVG(gross_margin_pct),0) AS a FROM sales"
    ).fetchone()
    if int(row["t"] or 0) > 0:
        total_sales, total_cost, total_margin, avg_margin = row["t"], row["c"], row["m"], row["a"]
    else:
        total_sales = conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM quotes WHERE COALESCE(status,'') "
            "IN ('Aprobada','Aprobado','Aceptada','Vendida','Facturada','Cerrada')"
        ).fetchone()[0]
        total_cost = conn.execute("""
            SELECT COALESCE(SUM(qi.quantity * COALESCE(inv.cost_unit,0)),0)
            FROM quote_items qi JOIN quotes q ON q.id=qi.quote_id
            LEFT JOIN inventory inv ON inv.sku=qi.sku
            WHERE COALESCE(q.status,'') IN ('Aprobada','Aprobado','Aceptada','Vendida','Facturada','Cerrada')
              AND qi.item_type IN ('producto','insumo')
        """).fetchone()[0]
        total_margin = int(total_sales or 0) - int(total_cost or 0)
        avg_margin   = (float(total_margin) / float(total_sales)) if total_sales else 0

    low_stock      = conn.execute("SELECT COUNT(*) FROM inventory WHERE COALESCE(is_service,0)=0 AND COALESCE(stock_min,0)>0 AND stock_current<=stock_min").fetchone()[0]
    open_ot        = (conn.execute("SELECT COUNT(*) FROM work_orders WHERE COALESCE(status,'Pendiente') IN ('Pendiente','Agendada','En ejecución','Abierta','En proceso')").fetchone()[0]
                    + conn.execute("SELECT COUNT(*) FROM projects WHERE COALESCE(status,'Pendiente') IN ('Aprobado','Aprobada','En ejecución','Pendiente')").fetchone()[0])
    total_inventory= conn.execute("SELECT COUNT(*) FROM inventory WHERE is_service=0").fetchone()[0]
    total_clients  = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    pending_quotes = conn.execute("SELECT COUNT(*) FROM quotes WHERE COALESCE(status,'Borrador') IN ('Borrador','Enviada','Pendiente')").fetchone()[0]
    total_projects = conn.execute("SELECT COUNT(*) FROM projects WHERE COALESCE(is_active,1)=1").fetchone()[0]
    conn.close()

    # ── Hero Banner ──────────────────────────────────────────────────────────
    from datetime import date
    weekdays_es = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    months_es   = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
    today = date.today()
    fecha_str = f"{weekdays_es[today.weekday()]}, {today.day} de {months_es[today.month-1]} {today.year}"

    st.markdown(f"""
    <div class="hero-banner">
        <div class="hero-eyebrow">Dashboard Ejecutivo</div>
        <div class="hero-title">Panel de Control</div>
        <div class="hero-subtitle">
            Vista consolidada · Ventas, operación técnica e inventario
            <span style="margin-left:1.2rem; color:#334155;">📅 {fecha_str}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Fila 1: KPIs comerciales ─────────────────────────────────────────────
    st.markdown('<div style="margin-bottom:.4rem; font-family:\'Outfit\',sans-serif; font-size:.72rem; font-weight:700; color:#334155; text-transform:uppercase; letter-spacing:.1em;">Resumen Comercial</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        dashboard_kpi_card("Ventas totales", money(total_sales),
                           "Acumulado histórico", "💰", "#3b82f6")
    with c2:
        dashboard_kpi_card("Margen bruto", money(total_margin),
                           "Rentabilidad generada", "📈", "#10b981")
    with c3:
        delta_class = "positive" if avg_margin * 100 >= 25 else ""
        dashboard_kpi_card("Margen promedio", f"{avg_margin*100:.1f}%",
                           "Promedio histórico", "🎯", "#10b981", delta_class)
    with c4:
        dashboard_kpi_card("Costo materiales", money(total_cost),
                           "Directo acumulado", "🧱", "#f59e0b")

    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)

    # ── Fila 2: KPIs operacionales ───────────────────────────────────────────
    st.markdown('<div style="margin-bottom:.4rem; font-family:\'Outfit\',sans-serif; font-size:.72rem; font-weight:700; color:#334155; text-transform:uppercase; letter-spacing:.1em;">Operación</div>', unsafe_allow_html=True)
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        warn = "warning" if int(open_ot) > 3 else ""
        dashboard_kpi_card("OT / Proyectos activos", str(int(open_ot)),
                           "Carga operativa actual", "🛠️", "#8b5cf6", warn)
    with c6:
        warn2 = "warning" if int(low_stock) > 0 else "positive"
        delta2 = f"⚠️ {int(low_stock)} productos críticos" if int(low_stock) > 0 else "✅ Todo en orden"
        dashboard_kpi_card("Stock bajo mínimo", str(int(low_stock)),
                           delta2, "📦", "#ef4444" if low_stock else "#10b981", warn2)
    with c7:
        dashboard_kpi_card("Cotizaciones pendientes", str(int(pending_quotes)),
                           "Borrador / Enviada", "🧾", "#f59e0b")
    with c8:
        dashboard_kpi_card("Clientes activos", str(int(total_clients)),
                           f"{int(total_inventory)} productos registrados", "👤", "#3b82f6")

    st.markdown("<div style='height:.8rem'></div>", unsafe_allow_html=True)

    # ── Cuerpo del dashboard ─────────────────────────────────────────────────
    left_col, right_col = st.columns([1.4, 1])

    with left_col:
        # Tabla stock crítico
        st.markdown("""
        <div class="section-card" style="padding:.9rem 1.1rem .5rem 1.1rem;">
            <div class="section-title">⚠️ Stock bajo mínimo</div>
            <div class="section-subtitle">Productos que requieren reposición inmediata.</div>
        </div>
        """, unsafe_allow_html=True)
        low_df = get_df("""
            SELECT sku AS SKU, description AS Descripción,
                   stock_current AS 'Stock actual', stock_min AS 'Mínimo',
                   sale_price AS 'Precio'
            FROM inventory
            WHERE COALESCE(is_service,0)=0 AND COALESCE(stock_min,0)>0
              AND stock_current <= stock_min
            ORDER BY stock_current ASC, sku
        """)
        if low_df.empty:
            st.success("✅ Sin alertas de stock. Todo en niveles normales.")
        else:
            st.dataframe(low_df, use_container_width=True, hide_index=True, height=260,
                         column_config={
                             "SKU":          st.column_config.TextColumn("SKU"),
                             "Descripción":  st.column_config.TextColumn("Descripción"),
                             "Stock actual": st.column_config.NumberColumn("Stock actual", format="%d"),
                             "Mínimo":       st.column_config.NumberColumn("Mínimo",       format="%d"),
                             "Precio":       st.column_config.NumberColumn("Precio venta", format="$ %d"),
                         })

        st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)

        # OT activas
        st.markdown("""
        <div class="section-card" style="padding:.9rem 1.1rem .5rem 1.1rem;">
            <div class="section-title">📋 OT activas</div>
            <div class="section-subtitle">Órdenes de trabajo en ejecución o pendientes.</div>
        </div>
        """, unsafe_allow_html=True)
        ot_df = get_dashboard_work_orders_df(8)
        if ot_df.empty:
            st.info("No hay órdenes de trabajo activas.")
        else:
            st.dataframe(ot_df, use_container_width=True, hide_index=True, height=220)

    with right_col:
        # Accesos rápidos con HTML puro
        st.markdown("""
        <div class="section-card" style="padding:.9rem 1.1rem 1rem 1.1rem;">
            <div class="section-title">⚡ Accesos Rápidos</div>
            <div class="section-subtitle">Atajos a las áreas más usadas.</div>
        </div>
        """, unsafe_allow_html=True)

        shortcuts = [
            ("📦 Inventario",     "Inventario"),
            ("🧾 Cotización",     "Cotización"),
            ("🧭 Flujo Guiado",   "Flujo Guiado"),
            ("👤 Clientes",       "Clientes"),
            ("📋 OT",             "OT"),
            ("🛠️ Proyectos",     "Proyectos"),
        ]
        q1, q2 = st.columns(2)
        for i, (label, tab) in enumerate(shortcuts):
            col = q1 if i % 2 == 0 else q2
            with col:
                if st.button(label, use_container_width=True, key=f"home_{tab}"):
                    st.session_state["current_tab"] = tab
                    st.rerun()

        st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)

        # Últimas cotizaciones
        st.markdown("""
        <div class="section-card" style="padding:.9rem 1.1rem .5rem 1.1rem;">
            <div class="section-title">🧾 Últimas cotizaciones</div>
        </div>
        """, unsafe_allow_html=True)
        cot_df = get_df("""
            SELECT q.quote_number AS 'N°', c.name AS Cliente,
                   q.status AS Estado, q.total AS Total
            FROM quotes q LEFT JOIN clients c ON c.id=q.client_id
            ORDER BY q.id DESC LIMIT 6
        """)
        if not cot_df.empty:
            cot_df["Total"] = cot_df["Total"].apply(money)
            st.dataframe(cot_df, use_container_width=True, hide_index=True, height=210)
        else:
            st.info("Sin cotizaciones aún.")
