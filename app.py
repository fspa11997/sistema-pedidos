import psycopg2.extras
import pytz
import os
from datetime import datetime
from flask import Flask, flash, render_template, session, redirect, request

from db import (
    validar_usuario,
    obtener_empresas,
    obtener_pedidos,
    agregar_pedido,
    cambiar_estado,
    eliminar_pedido,
    inicializar_db,
    recuperar_pedido,
    obtener_productos,
    obtener_pedidos_pendientes,
    obtener_pedidos_entregados,
    obtener_pedidos_eliminados,
    total_ventas_dia,
    total_ventas_mes,
    producto_top_mes,
    crear_factura,
    registrar_compra,
    obtener_inventario,
    obtener_detalles_factura,
    obtener_factura,
    obtener_facturas,
    conectar,
    crear_cliente,
    obtener_clientes,
    registrar_abono,
    validar_factura,
    a_colombia,
    ahora_utc,
    formatear_colombia
)


app = Flask(__name__)
app.secret_key = "secreto"

zona_colombia = pytz.timezone("America/Bogota")
@app.route("/", methods=["GET", "POST"])
def login():
    empresas = obtener_empresas()

    if request.method == "POST":
        user = request.form["usuario"]
        pwd = request.form["password"]
        empresa_id = int(request.form.get("empresa"))

        if not empresa_id:
            return render_template("login.html", empresas=empresas, error="Selecciona una empresa")

        usuario = validar_usuario(user, pwd, empresa_id)

        if usuario:
            session["usuario"] = usuario["usuario"]
            session["rol"] = usuario["rol"]
            session["empresa_id"] = usuario["empresa_id"]

            return redirect("/dashboard")

        return render_template(
            "login.html",
            empresas=empresas,
            error="Credenciales inválidas"
        )

    return render_template("login.html", empresas=empresas)
# =========================
# DASHBOARD PRINCIPAL
# =========================
@app.route("/dashboard")
def dashboard(): 

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]
    rol = session.get("rol")

    # =========================
    # CONEXIÓN POSTGRESQL
    # =========================
    conn = conectar()
    cursor = conn.cursor()

    # =========================
    # USUARIOS
    # =========================
    if rol == "owner_global":
        cursor.execute("""
            SELECT
                usuarios.id,
                usuarios.usuario,
                usuarios.rol,
                COALESCE(empresas.nombre, 'Sin empresa') AS empresa
            FROM usuarios
            LEFT JOIN empresas
                ON empresas.id = usuarios.empresa_id
            ORDER BY usuarios.id DESC
        """)
    else:
        cursor.execute("""
            SELECT
                usuarios.id,
                usuarios.usuario,
                usuarios.rol,
                COALESCE(empresas.nombre, 'Sin empresa') AS empresa
            FROM usuarios
            LEFT JOIN empresas
                ON empresas.id = usuarios.empresa_id
            WHERE usuarios.empresa_id = %s
            ORDER BY usuarios.id DESC
        """, (empresa_id,))

    usuarios = cursor.fetchall()

    # =========================
    # FILTROS USUARIOS (PYTHON)
    # =========================
    usuario_filtro = request.args.get("usuario", "").strip().lower()
    rol_filtro = request.args.get("rol", "").strip().lower()

    if usuario_filtro:
        usuarios = [
            u for u in usuarios
            if usuario_filtro in (u["usuario"] or "").lower()
        ]

    if rol_filtro:
        usuarios = [
            u for u in usuarios
            if rol_filtro in (u["rol"] or "").lower()
        ]

    # =========================
    # DATOS DB (YA POSTGRES VIA db.py)
    # =========================
    empresas = obtener_empresas()

    total_dia = total_ventas_dia(empresa_id)
    total_mes = total_ventas_mes(empresa_id)
    top_producto = producto_top_mes(empresa_id)

    filtro = request.args.get("filtro", "todos")

    if filtro == "pendientes":
        pedidos = obtener_pedidos_pendientes(empresa_id)
    elif filtro == "entregados":
        pedidos = obtener_pedidos_entregados(empresa_id)
    elif filtro == "eliminados":
        pedidos = obtener_pedidos_eliminados(empresa_id)
    else:
        pedidos = obtener_pedidos(empresa_id)

    productos = obtener_productos(empresa_id)
    clientes = obtener_clientes(empresa_id)
    inventario = obtener_inventario(empresa_id)

    conn.close()

    return render_template(
        "dashboard.html",
        pedidos=pedidos,
        productos=productos,
        filtro=filtro,
        empresas=empresas,
        total_dia=total_dia,
        total_mes=total_mes,
        top_producto=top_producto,
        inventario=inventario,
        clientes=clientes,
        usuarios=usuarios
    )

@app.route("/entregar/<int:id>")
def entregar(id):

    if "usuario" not in session:
        return redirect("/")

    cambiar_estado(id, "entregado")
    return redirect("/pedidos")


@app.route("/recuperar/<int:id>")
def recuperar(id):

    if "usuario" not in session:
        return redirect("/")

    recuperar_pedido(id)
    return redirect("/pedidos")


@app.route("/crear_usuario", methods=["POST"])
def crear_usuario():

    if "rol" not in session or session["rol"] != "owner_global":
        return "No autorizado", 403

    usuario = request.form["usuario"]
    password = request.form["password"]
    rol = request.form["rol"]
    empresa_id = request.form["empresa_id"]

    import bcrypt

    conn = conectar()
    cursor = conn.cursor()

    # =========================
    # VERIFICAR SI EXISTE
    # =========================
    cursor.execute("""
        SELECT id
        FROM usuarios
        WHERE usuario = %s
    """, (usuario,))

    existe = cursor.fetchone()

    if existe:
        conn.close()
        return "❌ El usuario ya existe", 400

    # =========================
    # HASH PASSWORD
    # =========================
    hash_password = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    # =========================
    # INSERTAR USUARIO
    # =========================
    cursor.execute("""
        INSERT INTO usuarios (usuario, password, rol, empresa_id)
        VALUES (%s, %s, %s, %s)
    """, (
        usuario,
        hash_password,
        rol,
        empresa_id
    ))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

@app.route("/eliminar_usuario/<int:id>", methods=["POST"])
def eliminar_usuario(id):

    if "rol" not in session or session["rol"] != "owner_global":
        return "No autorizado", 403

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM usuarios
        WHERE id = %s
    """, (id,))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

@app.route("/cambiar_password/<int:user_id>", methods=["POST"])
def cambiar_password(user_id):

    if "usuario" not in session:
        return redirect("/")

    # 🔐 solo admin global
    if session.get("rol") != "owner_global":
        return "No autorizado", 403

    nueva_password = request.form["password"]

    import bcrypt

    conn = conectar()
    cursor = conn.cursor()

    # =========================
    # HASH PASSWORD
    # =========================
    hash_password = bcrypt.hashpw(
        nueva_password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    # =========================
    # UPDATE USUARIO
    # =========================
    cursor.execute("""
        UPDATE usuarios
        SET password = %s
        WHERE id = %s
    """, (
        hash_password,
        user_id
    ))

    conn.commit()
    conn.close()

    return redirect("/dashboard")
# =========================
# CREAR PEDIDO

# =========================
@app.route("/crear_pedido", methods=["POST"])
def crear_pedido():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    cliente = request.form["cliente"]
    direccion = request.form["direccion"]
    ciudad = request.form["ciudad"]
    telefono = request.form["telefono"]
    domiciliario = request.form.get("domiciliario", "")
    tipo_precio = request.form.get("tipo_precio", "")

    productos = request.form.getlist("producto[]")
    cantidades = request.form.getlist("cantidad[]")
    pesos = request.form.getlist("peso[]")

    for i in range(len(productos)):

        agregar_pedido(
            cliente=cliente,
            producto=productos[i],
            direccion=direccion,
            ciudad=ciudad,
            telefono=telefono,
            domiciliario=domiciliario,
            cantidad=int(cantidades[i] or 0),
            peso=float(pesos[i] or 0),
            precio=0,   # opcional (ya lo calculas luego en DB si quieres)
            abono=0,
            tipo_precio=tipo_precio,
            empresa_id=empresa_id
        )

    return redirect("/dashboard")

# CREAR EMPRESAS
@app.route("/crear_empresa", methods=["POST"])
def crear_empresa():

    if "rol" not in session or session["rol"] != "owner_global":
        return "No autorizado", 403

    nombre = request.form["nombre"]

    conn = conectar()
    cursor = conn.cursor()

    # 🔍 VALIDAR SI YA EXISTE
    cursor.execute("""
        SELECT id FROM empresas WHERE nombre = %s
    """, (nombre,))

    if cursor.fetchone():
        conn.close()
        return redirect("/dashboard")

    # ✅ INSERTAR SI NO EXISTE
    cursor.execute("""
        INSERT INTO empresas (nombre)
        VALUES (%s)
    """, (nombre,))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

#ELIMINAR EMPRESA
@app.route("/eliminar_empresa/<int:id>")
def eliminar_empresa(id):

    if "rol" not in session or session["rol"] != "owner_global":
        return "No autorizado", 403

    conn = conectar()
    cursor = conn.cursor()

    # 🔴 BORRAR PRIMERO DATOS RELACIONADOS
    cursor.execute("""
        DELETE FROM usuarios
        WHERE empresa_id = %s
    """, (id,))

    cursor.execute("""
        DELETE FROM pedidos
        WHERE empresa_id = %s
    """, (id,))

    cursor.execute("""
        DELETE FROM productos
        WHERE empresa_id = %s
    """, (id,))

    # 🔥 BORRAR EMPRESA
    cursor.execute("""
        DELETE FROM empresas
        WHERE id = %s
    """, (id,))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

# =========================
# CAMBIAR ESTADO
# =========================
@app.route("/estado/<int:id>")
def estado(id):

    if "usuario" not in session:
        return redirect("/")

    cambiar_estado(id)

    return redirect("/dashboard")


# =========================
# ELIMINAR
# =========================
from db import conectar

def eliminar_pedido(id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM pedidos
        WHERE id = %s
    """, (id,))

    conn.commit()
    conn.close()


# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/crear_factura", methods=["POST"])
def crear_factura_route():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    # =========================
    # DATOS CLIENTE
    # =========================
    cliente = request.form.get("cliente", "").strip()
    direccion = request.form.get("direccion", "").strip()
    ciudad = request.form.get("ciudad", "").strip()
    telefono = request.form.get("telefono", "").strip()

    tipo_id = request.form.get("tipo_id", "").strip()
    identificacion = request.form.get("identificacion", "").strip()

    domiciliario = request.form.get("domiciliario", "").strip()

    tipo_precio = request.form.get("tipo_precio", "").strip()
    tipo_venta = request.form.get("tipo_venta", "contado").strip()
    forma_pago = request.form.get("forma_pago")
    plazo_pago = request.form.get("plazo_pago", "").strip()

    abono_raw = request.form.get("abono")

    # =========================
    # VALIDACIÓN BÁSICA (SIN RETURN 400)
    # =========================
    if not cliente:
        flash("El cliente es obligatorio", "error")
        return redirect("/dashboard")

    if not direccion:
        flash("La dirección es obligatoria", "error")
        return redirect("/dashboard")

    if not ciudad:
        flash("La ciudad es obligatoria", "error")
        return redirect("/dashboard")

    if not telefono:
        flash("El teléfono es obligatorio", "error")
        return redirect("/dashboard")

    if not identificacion:
        flash("La identificación es obligatoria", "error")
        return redirect("/dashboard")

    # 🔥 DOMICILIARIO OBLIGATORIO (ya corregido)
    if not domiciliario:
        flash("El domiciliario es obligatorio", "error")
        return redirect("/dashboard")

    # =========================
    # PRODUCTOS
    # =========================
    productos = request.form.getlist("producto[]")
    cantidades = request.form.getlist("cantidad[]")
    pesos = request.form.getlist("peso[]")

    if not productos:
        flash("Debe agregar al menos un producto", "error")
        return redirect("/dashboard")

    # =========================
    # VALIDAR PRODUCTOS
    # =========================
    for i in range(len(productos)):

        try:
            cantidad = float(cantidades[i] or 0)
            peso = float(pesos[i] or 0)
        except:
            flash("Error en cantidad o peso", "error")
            return redirect("/dashboard")

        if cantidad <= 0:
            flash("La cantidad debe ser mayor a 0", "error")
            return redirect("/dashboard")

        if peso <= 0:
            flash("El peso debe ser mayor a 0", "error")
            return redirect("/dashboard")

    # =========================
    # ABONO
    # =========================
    try:
        abono = float(abono_raw) if abono_raw not in [None, ""] else 0
    except:
        flash("Abono inválido", "error")
        return redirect("/dashboard")

    # =========================
    # REGLAS POR TIPO
    # =========================
    if tipo_venta == "credito":

        if not plazo_pago:
            flash("En ventas a crédito la fecha límite de pago es obligatoria", "error")
            return redirect("/dashboard")

        if abono < 0:
            flash("El abono no puede ser negativo", "error")
            return redirect("/dashboard")

    elif tipo_venta == "contado":
        abono = 0  # contado siempre 0

    else:
        flash("Tipo de venta inválido", "error")
        return redirect("/dashboard")

    # =========================
    # CONEXIÓN BD
    # =========================
    conn = conectar()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    productos_factura = []

    for i in range(len(productos)):

        producto = productos[i]
        cantidad = float(cantidades[i])
        peso = float(pesos[i])

        cursor.execute("""
            SELECT * FROM productos
            WHERE nombre = %s AND empresa_id = %s
        """, (producto, empresa_id))

        producto_db = cursor.fetchone()

        if not producto_db:
            continue

        if tipo_precio == "mayorista":
            precio_unitario = producto_db["precio_mayorista"]
        elif tipo_precio == "individual":
            precio_unitario = producto_db["precio_individual"]
        elif tipo_precio == "mostrador":
            precio_unitario = producto_db["precio_mostrador"]
        else:
            precio_unitario = 0

        productos_factura.append({
            "producto": producto,
            "cantidad": cantidad,
            "peso": peso,
            "precio": precio_unitario
        })

    conn.close()

    # =========================
    # CLIENTE FORMATEADO
    # =========================
    cliente_final = f"{cliente} - NIT: {identificacion}" if tipo_id == "nit" else f"{cliente} - CC: {identificacion}"

    # =========================
    # CREAR FACTURA
    # =========================
    resultado = crear_factura(
        cliente=cliente_final,
        direccion=direccion,
        ciudad=ciudad,
        telefono=telefono,
        empresa_id=empresa_id,
        productos=productos_factura,
        tipo_precio=tipo_precio,
        tipo_venta=tipo_venta,
        forma_pago=forma_pago,
        plazo_pago=plazo_pago,
        abono=abono,
        domiciliario=domiciliario
    )

    if isinstance(resultado, dict) and "error" in resultado:
        flash(resultado["error"], "error")
        return redirect("/dashboard")

    factura_id = resultado

    # =========================
    # PEDIDOS
    # =========================
    for p in productos_factura:

        agregar_pedido(
            cliente=cliente_final,
            producto=p["producto"],
            direccion=direccion,
            ciudad=ciudad,
            telefono=telefono,
            domiciliario=domiciliario,
            cantidad=p["cantidad"],
            peso=p["peso"],
            precio=p["precio"] * p["peso"],
            abono=abono,
            tipo_precio=tipo_precio,
            empresa_id=empresa_id
        )

    return redirect(f"/factura/{factura_id}")
       

@app.route("/registrar_compra", methods=["POST"])
def registrar_compra_route():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    producto = request.form["producto"]
    cantidad = int(request.form.get("cantidad") or 0)
    peso = float(request.form.get("peso") or 0)

    registrar_compra(producto, cantidad, peso, empresa_id)

    return redirect("/dashboard")

@app.route("/factura/<int:id>")
def ver_factura(id):

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    factura = obtener_factura(id, empresa_id)
    detalles = obtener_detalles_factura(id)

    if not factura:
        return "Factura no encontrada o no pertenece a esta empresa", 404

    return render_template(
        "factura.html",
        factura=factura,
        detalles=detalles
    )

@app.route("/facturas")
def ver_facturas():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    conn = conectar()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # =========================
    # FILTROS
    # =========================
    cliente = request.args.get("cliente", "").strip()
    factura = request.args.get("factura", "").strip()
    fecha = request.args.get("fecha", "").strip()

    query = """
        SELECT *
        FROM facturas
        WHERE empresa_id = %s
    """

    params = [empresa_id]

    # 🔍 filtro cliente
    if cliente:
        query += " AND cliente ILIKE %s"
        params.append(f"%{cliente}%")

    # 🔍 filtro factura ID
    if factura:
        query += " AND id::text ILIKE %s"
        params.append(f"%{factura}%")

    # 🔍 filtro fecha (CORRECTO: sin AT TIME ZONE)
    if fecha:
        query += " AND fecha::date = %s"
        params.append(fecha)

    query += " ORDER BY id DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    # =========================
    # CONVERSIÓN DE FECHA (COMO CARTERA)
    # =========================
    facturas = []

    for f in rows:
        f["fecha"] = a_colombia(f["fecha"])
        facturas.append(f)

    return render_template(
        "facturas.html",
        facturas=facturas
    )



@app.route("/facturar_empresa")
def facturar_empresa():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    factura_id = crear_factura(
        empresa_id=empresa_id,
        modo="pendientes"
    )

    if not factura_id:
        return "No hay pedidos pendientes", 400

    return redirect(f"/factura/{factura_id}")

@app.route("/crear_producto", methods=["POST"])
def crear_producto():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    nombre = request.form["nombre"]
    precio_mayorista = float(request.form["precio_mayorista"] or 0)
    precio_individual = float(request.form["precio_individual"] or 0)
    precio_mostrador = float(request.form["precio_mostrador"] or 0)
    costo = float(request.form["costo"] or 0)

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO productos (
            nombre,
            precio_mayorista,
            precio_individual,
            precio_mostrador,
            costo,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        nombre,
        precio_mayorista,
        precio_individual,
        precio_mostrador,
        costo,
        empresa_id
    ))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

@app.route("/eliminar_producto/<int:id>")
def eliminar_producto(id):

    if "usuario" not in session:
        return redirect("/")

    if session.get("rol") == "vendedor":
        return "No autorizado", 403

    empresa_id = session["empresa_id"]

    conn = conectar()
    cursor = conn.cursor()

    # 🔍 BUSCAR NOMBRE PRODUCTO
    cursor.execute("""
        SELECT nombre
        FROM productos
        WHERE id = %s AND empresa_id = %s
    """, (id, empresa_id))

    producto = cursor.fetchone()

    if producto:

        nombre_producto = producto["nombre"] if isinstance(producto, dict) else producto[0]

        # 🗑 ELIMINAR INVENTARIO RELACIONADO
        cursor.execute("""
            DELETE FROM inventario
            WHERE producto = %s
            AND empresa_id = %s
        """, (
            nombre_producto,
            empresa_id
        ))

        # 🗑 ELIMINAR PRODUCTO
        cursor.execute("""
            DELETE FROM productos
            WHERE id = %s
            AND empresa_id = %s
        """, (
            id,
            empresa_id
        ))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

@app.route("/ventas")
def ventas():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]
        # =====================================================
    # FILTROS
    # =====================================================
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    desde_mes = request.args.get("desde_mes")
    hasta_mes = request.args.get("hasta_mes")

    conn = conectar()

    # 🔥 IMPORTANTE
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # =====================================================
    # FACTURAS (VENTAS REALES)
    # =====================================================
    cursor.execute("""
        SELECT *
        FROM facturas
        WHERE empresa_id = %s
        ORDER BY id DESC
    """, (empresa_id,))

    ventas = cursor.fetchall()

    # 🔥 NORMALIZAR DATOS
    for v in ventas:

        v["total"] = float(v.get("total") or 0)
        v["abono"] = float(v.get("abono") or 0)

        if v.get("fecha"):
            v["fecha"] = a_colombia(v["fecha"])

    # =====================================================
    # RESUMEN DIARIO
    # =====================================================
    cursor.execute("""
        SELECT 
            COALESCE(SUM(total),0) AS facturado,
            COALESCE(SUM(abono),0) AS abonado,
            COALESCE(SUM(total - abono),0) AS deben
        FROM facturas
        WHERE empresa_id = %s
        AND (fecha AT TIME ZONE 'America/Bogota')::date =
            (NOW() AT TIME ZONE 'America/Bogota')::date
    """, (empresa_id,))

    dia = cursor.fetchone() or {}

    dia["facturado"] = float(dia.get("facturado") or 0)
    dia["abonado"] = float(dia.get("abonado") or 0)
    dia["deben"] = float(dia.get("deben") or 0)

   # =====================================================
    # FORMAS DE PAGO HOY (CORREGIDO)
    # =====================================================

    cursor.execute("""
        SELECT
            forma_pago,
            SUM(valor) AS total
        FROM (

            -- Ventas de contado (SOLO contado)
            SELECT
                COALESCE(forma_pago,'Sin especificar') AS forma_pago,
                COALESCE(total,0) AS valor
            FROM facturas
            WHERE empresa_id = %s
            AND tipo_venta = 'contado'
            AND (fecha AT TIME ZONE 'America/Bogota')::date =
                (NOW() AT TIME ZONE 'America/Bogota')::date

            UNION ALL

            -- Abonos de cartera
            SELECT
                COALESCE(forma_pago,'Sin especificar') AS forma_pago,
                COALESCE(abono,0) AS valor
            FROM pagos_credito
            WHERE empresa_id = %s
            AND (fecha AT TIME ZONE 'America/Bogota')::date =
                (NOW() AT TIME ZONE 'America/Bogota')::date

        ) t

        GROUP BY forma_pago
        ORDER BY total DESC
    """, (empresa_id, empresa_id))

    formas_pago_dia = cursor.fetchall()

    for f in formas_pago_dia:
        f["total"] = float(f.get("total") or 0)

    # =====================================================
    # RESUMEN MENSUAL
    # =====================================================
    cursor.execute("""
        SELECT 
            COALESCE(SUM(total),0) AS facturado,
            COALESCE(SUM(abono),0) AS abonado,
            COALESCE(SUM(total - abono),0) AS deben
        FROM facturas
        WHERE empresa_id = %s
        AND DATE_TRUNC(
            'month',
            fecha AT TIME ZONE 'America/Bogota'
        ) = DATE_TRUNC(
            'month',
            NOW() AT TIME ZONE 'America/Bogota'
        )
    """, (empresa_id,))

    mes = cursor.fetchone() or {}

    mes["facturado"] = float(mes.get("facturado") or 0)
    mes["abonado"] = float(mes.get("abonado") or 0)
    mes["deben"] = float(mes.get("deben") or 0)

    # =====================================================
    # FORMAS DE PAGO MES
    # =====================================================

    cursor.execute("""
        SELECT
            forma_pago,
            SUM(valor) AS total
        FROM (

            -- Ventas del mes
            SELECT
                COALESCE(forma_pago,'Sin especificar') AS forma_pago,
                COALESCE(abono,0) AS valor
            FROM facturas
            WHERE empresa_id = %s
            AND DATE_TRUNC(
                'month',
                fecha AT TIME ZONE 'America/Bogota'
            ) = DATE_TRUNC(
                'month',
                NOW() AT TIME ZONE 'America/Bogota'
            )

            UNION ALL

            -- Abonos de cartera del mes
            SELECT
                COALESCE(forma_pago,'Sin especificar') AS forma_pago,
                COALESCE(abono,0) AS valor
            FROM pagos_credito
            WHERE empresa_id = %s
            AND DATE_TRUNC(
                'month',
                fecha AT TIME ZONE 'America/Bogota'
            ) = DATE_TRUNC(
                'month',
                NOW() AT TIME ZONE 'America/Bogota'
            )

        ) t

        GROUP BY forma_pago
        ORDER BY total DESC
    """, (empresa_id, empresa_id))

    formas_pago_mes = cursor.fetchall()

    for f in formas_pago_mes:
        f["total"] = float(f.get("total") or 0)

    # =====================================================
    # HISTÓRICO DIARIO
    # =====================================================

    query_diario = """
        SELECT
            (fecha AT TIME ZONE 'America/Bogota')::date AS dia,
            COALESCE(SUM(total),0) AS facturado,
            COALESCE(SUM(abono),0) AS abonado,
            COALESCE(SUM(total - abono),0) AS deben
        FROM facturas
        WHERE empresa_id = %s
    """

    params_diario = [empresa_id]

    if desde:
        query_diario += """
            AND (fecha AT TIME ZONE 'America/Bogota')::date >= %s
        """
        params_diario.append(desde)

    if hasta:
        query_diario += """
            AND (fecha AT TIME ZONE 'America/Bogota')::date <= %s
        """
        params_diario.append(hasta)

    query_diario += """
        GROUP BY (fecha AT TIME ZONE 'America/Bogota')::date
        ORDER BY dia DESC
    """

    cursor.execute(query_diario, params_diario)

    diario = cursor.fetchall()

    for d in diario:
        d["facturado"] = float(d.get("facturado") or 0)
        d["abonado"] = float(d.get("abonado") or 0)
        d["deben"] = float(d.get("deben") or 0)

       # =====================================================
    # HISTÓRICO MENSUAL
    # =====================================================

    query_mensual = """
        SELECT
            TO_CHAR(
                fecha AT TIME ZONE 'America/Bogota',
                'YYYY-MM'
            ) AS mes,

            COALESCE(SUM(total),0) AS facturado,
            COALESCE(SUM(abono),0) AS abonado,
            COALESCE(SUM(total - abono),0) AS deben

        FROM facturas
        WHERE empresa_id = %s
    """

    params_mensual = [empresa_id]

    if desde_mes:
        query_mensual += """
            AND DATE_TRUNC(
                'month',
                fecha AT TIME ZONE 'America/Bogota'
            ) >= DATE_TRUNC('month', %s::date)
        """
        params_mensual.append(desde_mes)

    if hasta_mes:
        query_mensual += """
            AND DATE_TRUNC(
                'month',
                fecha AT TIME ZONE 'America/Bogota'
            ) <= DATE_TRUNC('month', %s::date)
        """
        params_mensual.append(hasta_mes)

    query_mensual += """
        GROUP BY TO_CHAR(
            fecha AT TIME ZONE 'America/Bogota',
            'YYYY-MM'
        )
        ORDER BY mes DESC
    """

    cursor.execute(query_mensual, params_mensual)

    mensual = cursor.fetchall()

    for m in mensual:
        m["facturado"] = float(m.get("facturado") or 0)
        m["abonado"] = float(m.get("abonado") or 0)
        m["deben"] = float(m.get("deben") or 0)

    conn.close()

    return render_template(
        "ventas.html",
        ventas=ventas,
        dia=dia,
        mes=mes,
        diario=diario,
        mensual=mensual,
        formas_pago_dia=formas_pago_dia,
        formas_pago_mes=formas_pago_mes
    )

@app.route("/reportes")
def reportes():

    if "usuario" not in session:
        return redirect("/")

    if session.get("rol") == "vendedor":
        return "No autorizado", 403

    empresa_id = session["empresa_id"]

    conn = conectar()
    cursor = conn.cursor()

    # =========================
    # TOTAL VENDIDO
    # =========================
    cursor.execute("""
        SELECT COALESCE(SUM(precio), 0) as total
        FROM pedidos
        WHERE empresa_id = %s
        AND eliminado = 0
    """, (empresa_id,))

    total = cursor.fetchone()[0]

    # =========================
    # TOTAL PEDIDOS
    # =========================
    cursor.execute("""
        SELECT COUNT(*) as total_pedidos
        FROM pedidos
        WHERE empresa_id = %s
        AND eliminado = 0
    """, (empresa_id,))

    total_pedidos = cursor.fetchone()[0]

    # =========================
    # PRODUCTO MÁS VENDIDO
    # =========================
    cursor.execute("""
        SELECT producto, COUNT(*) as total
        FROM pedidos
        WHERE empresa_id = %s
        GROUP BY producto
        ORDER BY total DESC
        LIMIT 1
    """, (empresa_id,))

    row = cursor.fetchone()

    if row:
        top_producto = {
            "producto": row[0],
            "total": row[1]
        }
    else:
        top_producto = None

    conn.close()

    return render_template(
        "reportes.html",
        total=total,
        total_pedidos=total_pedidos,
        top_producto=top_producto
    )

@app.route("/crear_cliente", methods=["POST"])
def crear_cliente_route():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    crear_cliente(
        request.form["nombre"],
        request.form["direccion"],
        request.form["ciudad"],
        request.form["telefono"],
        request.form["tipo_id"],
        request.form["identificacion"],
        empresa_id
    )

    return redirect("/clientes")

@app.route("/clientes")
def clientes():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    clientes = obtener_clientes(empresa_id)

    return render_template(
        "clientes.html",
        clientes=clientes
    )

@app.route("/pedidos")
def pedidos():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    filtro = request.args.get("filtro", "pendientes")
    buscar = request.args.get("buscar", "").strip().lower()
    fecha = request.args.get("fecha", "")
    domiciliario = request.args.get("domiciliario", "").strip().lower()

    conn = conectar()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = """
        SELECT *
        FROM pedidos
        WHERE empresa_id = %s
    """

    params = [empresa_id]

    # =========================
    # FILTROS ESTADO
    # =========================
    if filtro == "pendientes":
        query += " AND estado = 'pendiente' AND eliminado = 0"
    elif filtro == "entregados":
        query += " AND estado = 'entregado' AND eliminado = 0"
    elif filtro == "eliminados":
        query += " AND eliminado = 1"
    elif filtro == "todos":
        query += " AND eliminado = 0"

    # =========================
    # BUSQUEDA
    # =========================
    if buscar:
        query += " AND (LOWER(cliente) LIKE %s OR LOWER(producto) LIKE %s)"
        params += [f"%{buscar}%", f"%{buscar}%"]

    # =========================
    # FECHA (CORREGIDA)
    # =========================
    if fecha:
        query += " AND fecha::date = %s"
        params.append(fecha)

    # =========================
    # DOMICILIARIO
    # =========================
    if domiciliario:
        query += " AND LOWER(COALESCE(domiciliario,'')) LIKE %s"
        params.append(f"%{domiciliario}%")

    query += " ORDER BY id DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # =========================
    # NORMALIZACIÓN + FECHA (CLAVE)
    # =========================
    pedidos = []

    for item in rows:

        # 🔥 conversión de fecha (igual que cartera)
        if "fecha" in item:
            item["fecha"] = a_colombia(item["fecha"])

        item["precio"] = float(item.get("precio") or 0)
        item["cantidad"] = int(item.get("cantidad") or 0)
        item["peso"] = float(item.get("peso") or 0)

        pedidos.append(item)

    conn.close()

    return render_template(
        "pedidos.html",
        pedidos=pedidos,
        filtro=filtro
    )

@app.route("/cartera")
def cartera():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    factura_id = request.args.get("id")
    cliente_filtro = request.args.get("cliente", "")
    estado = request.args.get("estado", "")
    fecha = request.args.get("fecha", "")

    conn = conectar()

    cursor = conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    )

    # =========================
    # QUERY PRINCIPAL
    # =========================
    query = """
        SELECT
            id,
            cliente,

            TO_CHAR(
                fecha AT TIME ZONE 'America/Bogota',
                'YYYY-MM-DD HH24:MI'
            ) AS fecha,

            plazo_pago,

            total,
            abono,

            (total - abono) AS saldo,

            CASE
                WHEN (total - abono) <= 0 THEN 'pagado'
                WHEN abono > 0 THEN 'parcial'
                ELSE 'pendiente'
            END AS estado_calculado

        FROM facturas
        WHERE empresa_id = %s
    """

    params = [empresa_id]

    # =========================
    # FILTROS
    # =========================

    if factura_id:
        query += " AND id = %s"
        params.append(factura_id)

    if cliente_filtro:
        query += " AND LOWER(cliente) LIKE %s"
        params.append(f"%{cliente_filtro.lower()}%")

    if fecha:
        query += """
            AND (
                fecha AT TIME ZONE 'America/Bogota'
            )::date = %s
        """
        params.append(fecha)

    if estado:
        query += """
            AND CASE
                WHEN (total - abono) <= 0 THEN 'pagado'
                WHEN abono > 0 THEN 'parcial'
                ELSE 'pendiente'
            END = %s
        """
        params.append(estado)

    query += " ORDER BY id DESC"

    # =========================
    # EJECUTAR
    # =========================

    cursor.execute(query, params)

    rows = cursor.fetchall()

    facturas = []

    for item in rows:

        item["total"] = float(item.get("total") or 0)
        item["abono"] = float(item.get("abono") or 0)
        item["saldo"] = float(item.get("saldo") or 0)

        facturas.append(item)

    # =========================
    # TOTALES
    # =========================

    cursor.execute("""
        SELECT
            COALESCE(SUM(total),0) AS total_facturado,
            COALESCE(SUM(abono),0) AS total_abonado,
            COALESCE(SUM(total - abono),0) AS total_deben
        FROM facturas
        WHERE empresa_id = %s
    """, (empresa_id,))

    t = cursor.fetchone()

    total_facturado = float(t["total_facturado"] or 0)
    total_abonado = float(t["total_abonado"] or 0)
    total_deben = float(t["total_deben"] or 0)

    conn.close()

    return render_template(
        "cartera.html",
        facturas=facturas,
        total_facturado=total_facturado,
        total_abonado=total_abonado,
        total_deben=total_deben
    )


@app.route("/abonar_credito", methods=["POST"])
def abonar_credito_route():

    if "usuario" not in session:
        return redirect("/")

    factura_id = request.form.get("factura_id")
    abono = request.form.get("abono")
    forma_pago = request.form["forma_pago"]
    observacion = request.form.get("observacion", "")

    if not factura_id or not abono:
        return "Datos incompletos", 400

    registrar_abono(
        factura_id=int(factura_id),
        abono=float(abono),
        observacion=observacion,
        forma_pago=forma_pago,
        empresa_id=session["empresa_id"]
    )
    flash("abono guardado", "success")
    return redirect("/cartera")

@app.route("/abonar_factura/<int:factura_id>", methods=["POST"])
def abonar_factura(factura_id):

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    abono_nuevo = float(request.form["abono"])
    observacion = request.form.get("observacion", "")
    fecha = ahora_utc()
    conn = conectar()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 🔎 traer factura
    cursor.execute("""
        SELECT *
        FROM facturas
        WHERE id = %s AND empresa_id = %s
    """, (factura_id, empresa_id))

    factura = cursor.fetchone()

    if not factura:
        conn.close()
        return "Factura no existe", 404

    total = factura["total"]
    abono_actual = factura["abono"] or 0

    nuevo_abono = abono_actual + abono_nuevo
    saldo = total - nuevo_abono

    if saldo <= 0:
        estado = "pagado"
        saldo = 0
    else:
        estado = "parcial"

    # 💰 actualizar factura
    cursor.execute("""
        UPDATE facturas
        SET abono = %s,
            estado = %s
        WHERE id = %s AND empresa_id = %s
    """, (nuevo_abono, estado, factura_id, empresa_id))

    # 📜 guardar historial
    cursor.execute("""
        INSERT INTO pagos_credito (
            factura_id,
            cliente,
            abono,
            fecha,
            observacion,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
            factura_id,
            factura["cliente"],
            abono_nuevo,
            fecha,
            observacion,
            empresa_id
        ))

    conn.commit()
    conn.close()

    return redirect("/cartera")

@app.route("/recibo_abono/<int:recibo_id>")
def ver_recibo_abono(recibo_id):

    if "usuario" not in session:
        return redirect("/")

    conn = conectar()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT 
            *,
            TO_CHAR(
                fecha AT TIME ZONE 'America/Bogota',
                'YYYY-MM-DD HH24:MI'
            ) AS fecha
        FROM recibos_abono
        WHERE id = %s
        AND empresa_id = %s
    """, (
        recibo_id,
        session["empresa_id"]
    ))

    recibo = cursor.fetchone()

    conn.close()

    return render_template(
        "recibo_abono.html",
        recibo=recibo
    )

@app.route("/historial_abonos/<int:factura_id>")
def historial_abonos(factura_id):

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    from db import obtener_historial_abonos

    pagos = obtener_historial_abonos(
        factura_id,
        empresa_id
    )

    return render_template(
        "historial_abonos.html",
        pagos=pagos,
        factura_id=factura_id
    )
# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

