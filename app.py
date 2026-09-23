import pytz
import os
from datetime import datetime
import barcode
from barcode.writer import SVGWriter
from flask import Flask, flash, render_template, session, redirect, request, Response
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
    obtener_empresas,
    total_ventas_dia,
    total_ventas_mes,
    facturas_emitidas_hoy,
    saldo_cartera,
    producto_top_mes,
    productos_top_5_mes,
    crear_factura, 
    registrar_compra,
    obtener_inventario,
    obtener_detalles_factura,
    obtener_factura,
    obtener_facturas,
    conectar,
    crear_cliente,
    obtener_clientes,
    registrar_abono
)



from db import inicializar_db
def seed():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:

        import bcrypt

        hash_password = bcrypt.hashpw(
            "1234".encode(),
            bcrypt.gensalt()
        ).decode("utf-8")

        cursor.execute("""
            INSERT INTO usuarios (usuario, password, rol, empresa_id)
            VALUES (%s, %s, %s, %s)
        """, ("superadmin", hash_password, "owner_global", 1))

        print("🔥 Usuario superadmin creado")

    conn.commit()
    conn.close()
    
inicializar_db()
seed()
print("🔥 DB inicializada")

app = Flask(__name__)
app.secret_key = "secreto"

zona_colombia = pytz.timezone("America/Bogota")
fecha_entrega = datetime.now(zona_colombia)
# =========================
# LOGIN
# =========================
@app.route("/", methods=["GET", "POST"])
def login():
    empresas = obtener_empresas()
    
    if request.method == "POST":
        user = request.form["usuario"]
        pwd = request.form["password"]
        

        usuario = validar_usuario(user, pwd)

        if usuario:

            session["usuario"] = usuario["usuario"]
            session["rol"] = usuario["rol"]
            session["empresa_id"] = usuario["empresa_id"]

            return redirect("/dashboard")

        return render_template("login.html", empresas=empresas, error="Credenciales inválidas")

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
    # CONEXIÓN
    # =========================
    conn = conectar()
    cursor = conn.cursor()

    # =========================
    # USUARIOS (OWNER GLOBAL / EMPRESA)
    # =========================
    if rol == "owner_global":
        cursor.execute("""
            SELECT
                usuarios.id,
                usuarios.usuario,
                usuarios.rol,
                COALESCE(empresas.nombre, 'Sin empresa') as empresa
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
                COALESCE(empresas.nombre, 'Sin empresa') as empresa
            FROM usuarios
            LEFT JOIN empresas
                ON empresas.id = usuarios.empresa_id
            WHERE usuarios.empresa_id = %s
            ORDER BY usuarios.id DESC
        """, (empresa_id,))

    usuarios = cursor.fetchall()

    # =========================
    # FILTROS USUARIOS
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
    # RESTO DEL DASHBOARD
    # =========================
    empresas = obtener_empresas()

    buscar = request.args.get("buscar", "")
    fecha = request.args.get("fecha")
    domiciliario_filtro = request.args.get("domiciliario", "")
    
    total_dia = total_ventas_dia(empresa_id)
    total_mes = total_ventas_mes(empresa_id)
    facturas_hoy = facturas_emitidas_hoy(empresa_id)
    cartera_pendiente = saldo_cartera(empresa_id)
    top_producto = producto_top_mes(empresa_id)
    top_5_productos = productos_top_5_mes(empresa_id)

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

    # =========================
    # RENDER
    # =========================
    

    return render_template(
        "dashboard.html",
        pedidos=pedidos,
        productos=productos,
        filtro=filtro,
        empresas=empresas,
        total_dia=total_dia,
        total_mes=total_mes,
        facturas_hoy=facturas_hoy,
        cartera_pendiente=cartera_pendiente,
        top_producto=top_producto,
        top_5_productos=top_5_productos,
        inventario=inventario,
        clientes=clientes,
        usuarios=usuarios
    )

@app.route("/entregar/<int:id>")
def entregar(id):
    cambiar_estado(id, "entregado")
    return redirect("/pedidos")


@app.route("/recuperar/<int:id>")
def recuperar(id):
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

    # 🔍 VERIFICAR SI YA EXISTE
    cursor.execute("""
        SELECT id FROM usuarios WHERE usuario = %s
    """, (usuario,))

    existe = cursor.fetchone()

    if existe:
        conn.close()
        return "❌ El usuario ya existe", 400

    hash_password = bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode("utf-8")

    cursor.execute("""
        INSERT INTO usuarios (usuario, password, rol, empresa_id)
        VALUES (%s, %s, %s, %s)
    """, (usuario, hash_password, rol, empresa_id))

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

    # 🔐 solo admin global o dueño
    if session.get("rol") != "owner_global":
        return "No autorizado", 403

    nueva_password = request.form["password"]

    import bcrypt
    
    hash_password = bcrypt.hashpw(
        nueva_password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET password = %s
        WHERE id = %s
    """, (hash_password, user_id))

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

    precio = float(request.form.get("precio") or 0)
    abono = float(request.form.get("abono") or 0)
    tipo_precio = request.form.get("tipo_precio", "")

    productos = request.form.getlist("producto[]")
    cantidades = request.form.getlist("cantidad[]")

    for i in range(len(productos)):

        agregar_pedido(
            cliente,
            productos[i],
            direccion,
            ciudad,
            telefono,
            domiciliario,
            int(cantidades[i]),
            precio,
            abono,
            tipo_precio,
            empresa_id
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
    cursor.execute("SELECT id FROM empresas WHERE nombre = %s", (nombre,))
    if cursor.fetchone():
        conn.close()
        return redirect("/dashboard")  # puedes luego mostrar mensaje

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
    cursor.execute("DELETE FROM usuarios WHERE empresa_id=%s", (id,))
    cursor.execute("DELETE FROM pedidos WHERE empresa_id=%s", (id,))
    cursor.execute("DELETE FROM productos WHERE empresa_id=%s", (id,))

    # 🔥 BORRAR EMPRESA
    cursor.execute("DELETE FROM empresas WHERE id=%s", (id,))

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
@app.route("/eliminar/<int:id>")
def eliminar(id):
    if "usuario" not in session:
        return redirect("/")

    eliminar_pedido(id)
    return redirect("/pedidos")


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

    tipo_id = request.form.get("tipo_id", "")
    identificacion = request.form.get("identificacion", "").strip()

    domiciliario = request.form.get("domiciliario", "").strip()

    tipo_precio = request.form.get("tipo_precio", "")
    tipo_venta = request.form.get("tipo_venta", "contado")

    plazo_pago = request.form.get("plazo_pago", "").strip()
    abono_raw = request.form.get("abono", "").strip()

    # =========================
    # VALIDACIONES CLIENTE
    # =========================
    if not cliente:
        flash("⚠️ Debes ingresar el cliente", "error")
        return redirect("/dashboard")

    if not direccion:
        flash("⚠️ Debes ingresar la dirección", "error")
        return redirect("/dashboard")

    if not ciudad:
        flash("⚠️ Debes ingresar la ciudad", "error")
        return redirect("/dashboard")

    if not telefono:
        flash("⚠️ Debes ingresar el teléfono", "error")
        return redirect("/dashboard")

    if not tipo_id or not identificacion:
        flash("⚠️ Debes ingresar identificación del cliente", "error")
        return redirect("/dashboard")

    if not domiciliario:
        flash("⚠️ Debes asignar un domiciliario", "error")
        return redirect("/dashboard")

    # =========================
    # PRODUCTOS
    # =========================
    productos = request.form.getlist("producto[]")
    cantidades = request.form.getlist("cantidad[]")

    if not productos:
        flash("⚠️ Debes agregar productos", "error")
        return redirect("/dashboard")

    # =========================
    # VALIDAR CANTIDAD (UNIDADES)
    # =========================
    for i in range(len(productos)):
        try:
            cantidad = int(cantidades[i])
        except:
            flash(f"⚠️ La cantidad de '{productos[i]}' debe ser un número entero", "error")
            return redirect("/dashboard")

        if cantidad <= 0:
            flash(f"⚠️ La cantidad de '{productos[i]}' debe ser mayor a 0", "error")
            return redirect("/dashboard")

    # =========================
    # VALIDACIÓN CRÉDITO
    # =========================
    if tipo_venta == "credito":

        if not plazo_pago:
            flash("⚠️ Debes definir el plazo de pago", "error")
            return redirect("/dashboard")

        if abono_raw == "":
            flash("⚠️ Debes ingresar abono para crédito", "error")
            return redirect("/dashboard")

    # =========================
    # NORMALIZAR ABONO
    # =========================
    try:
        abono = float(abono_raw or 0)
    except:
        flash("⚠️ El abono no es válido", "error")
        return redirect("/dashboard")

    # =========================
    # DB PRODUCTOS
    # =========================
    conn = conectar()
    cursor = conn.cursor()

    productos_factura = []

    for i in range(len(productos)):

        producto = productos[i]
        cantidad = int(cantidades[i])

        cursor.execute("""
            SELECT * FROM productos
            WHERE nombre=%s AND empresa_id=%s
        """, (producto, empresa_id))

        producto_db = cursor.fetchone()

        if not producto_db:
            continue

        if tipo_precio == "mayorista":
            precio_unitario = producto_db["precio_mayorista"]
        elif tipo_precio == "individual":
            precio_unitario = producto_db["precio_individual"]
        else:
            precio_unitario = producto_db["precio_mostrador"]

        productos_factura.append({
            "producto": producto,
            "cantidad": cantidad,
            "precio": precio_unitario
        })

    conn.close()

    # =========================
    # CLIENTE FINAL
    # =========================
    if tipo_id == "nit":
        cliente_final = f"{cliente} - NIT: {identificacion}"
    else:
        cliente_final = f"{cliente} - CC: {identificacion}"

    # =========================
    # CREAR FACTURA
    # =========================
    factura_id = crear_factura(
        cliente=cliente_final,
        direccion=direccion,
        ciudad=ciudad,
        telefono=telefono,
        empresa_id=empresa_id,
        productos=productos_factura,
        tipo_precio=tipo_precio,
        tipo_venta=tipo_venta,
        plazo_pago=plazo_pago,
        abono=abono,
        domiciliario=domiciliario
    )

    # =========================
    # CREAR PEDIDOS
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
            precio=p["precio"] * p["cantidad"],
            abono=abono,
            tipo_precio=tipo_precio,
            empresa_id=empresa_id
        )

    flash("Factura creada satisfactoriamente", "success")
    return redirect("/dashboard")
   
       

@app.route("/productos")
def productos_page():
    if "usuario" not in session:
        return redirect("/")
    empresa_id = session["empresa_id"]
    productos = obtener_productos(empresa_id)
    return render_template("productos.html", productos=productos)


@app.route("/inventario")
def inventario_page():
    if "usuario" not in session:
        return redirect("/")
    empresa_id = session["empresa_id"]
    productos = obtener_productos(empresa_id)
    inventario = obtener_inventario(empresa_id)
    return render_template("inventario.html", productos=productos, inventario=inventario)


@app.route("/registrar_compra", methods=["POST"])
def registrar_compra_route():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]
    codigo_barras = request.form.get("codigo_barras", "").strip()
    producto = request.form.get("producto", "").strip()
    cantidad = int(request.form.get("cantidad") or 0)

    if cantidad <= 0:
        return redirect("/inventario")

    if codigo_barras:
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nombre, codigo_barras
            FROM productos
            WHERE codigo_barras = %s AND empresa_id = %s AND activo = TRUE
            LIMIT 1
        """, (codigo_barras, empresa_id))
        p = cursor.fetchone()
        conn.close()

        if not p:
            return render_template(
                "inventario.html",
                productos=obtener_productos(empresa_id),
                inventario=obtener_inventario(empresa_id),
                error="No existe un producto con ese código de barras."
            )

        producto = p["nombre"]
        codigo_barras = p["codigo_barras"]

    registrar_compra(producto, cantidad, empresa_id, codigo_barras)
    return redirect("/inventario")


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
    cursor = conn.cursor()

    # =========================
    # FILTROS
    # =========================
    cliente = request.args.get("cliente", "")
    factura = request.args.get("factura", "")
    fecha = request.args.get("fecha", "")

    query = """
        SELECT *
        FROM facturas
        WHERE empresa_id = %s
    """

    params = [empresa_id]

    # 🔍 filtro cliente
    if cliente:
        query += " AND cliente LIKE %s"
        params.append(f"%{cliente}%")

    # 🔍 filtro factura ID
    if factura:
        query += " AND id::text LIKE %s"
        params.append(f"%{factura}%")

    # 🔍 filtro fecha
    if fecha:
        query += " AND fecha::date = %s"
        params.append(fecha)

    query += " ORDER BY id DESC"

    cursor.execute(query, params)

    facturas = cursor.fetchall()

    conn.close()
    
    return render_template(
        "facturas.html",
        facturas=facturas
    )



@app.route("/facturar_empresa")
def facturar_empresa():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    factura_id = crear_factura(empresa_id)

    if not factura_id:
        return "No hay pedidos pendientes", 400

    return redirect(f"/factura/{factura_id}")

@app.route("/crear_producto", methods=["POST"])
def crear_producto():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]
    nombre = request.form.get("nombre", "").strip()
    precio_mayorista = request.form.get("precio_mayorista") or 0
    precio_individual = request.form.get("precio_individual") or 0
    precio_mostrador = request.form.get("precio_mostrador") or 0
    costo = request.form.get("costo") or 0
    codigo_barras = request.form.get("codigo_barras", "").strip()

    try:
        cantidad = int(request.form.get("cantidad") or 0)
    except (TypeError, ValueError):
        cantidad = 0

    if not nombre:
        return render_template("productos.html",
            productos=obtener_productos(empresa_id),
            error="Debes indicar el nombre del producto.")

    if cantidad <= 0:
        return render_template("productos.html",
            productos=obtener_productos(empresa_id),
            error="La cantidad inicial debe ser un número entero mayor que 0.")

    conn = conectar()
    cursor = conn.cursor()

    if not codigo_barras:
        import secrets
        while True:
            codigo_barras = "770" + "".join(str(secrets.randbelow(10)) for _ in range(10))
            cursor.execute("""
                SELECT 1 FROM productos
                WHERE codigo_barras = %s AND empresa_id = %s
                LIMIT 1
            """, (codigo_barras, empresa_id))
            if not cursor.fetchone():
                break

    cursor.execute("""
        SELECT id FROM productos
        WHERE codigo_barras = %s AND empresa_id = %s
        LIMIT 1
    """, (codigo_barras, empresa_id))
    if cursor.fetchone():
        conn.close()
        return render_template("productos.html",
            productos=obtener_productos(empresa_id),
            error="Ya existe un producto con ese código de barras.")

    try:
        # 1. Crear el producto con su código de barras.
        cursor.execute("""
            INSERT INTO productos (
                nombre, precio_mayorista, precio_individual,
                precio_mostrador, costo, codigo_barras, empresa_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (nombre, precio_mayorista, precio_individual,
              precio_mostrador, costo, codigo_barras, empresa_id))

        # 2. Crear automáticamente su registro de inventario con la cantidad inicial.
        cursor.execute("""
            INSERT INTO inventario (producto, stock_unidades, codigo_barras, empresa_id)
            VALUES (%s, %s, %s, %s)
        """, (nombre, cantidad, codigo_barras, empresa_id))

        # 3. Dejar trazabilidad de la carga inicial.
        cursor.execute("""
            INSERT INTO movimientos_inventario
                (producto, tipo, cantidad, fecha, empresa_id)
            VALUES (%s, 'entrada', %s, NOW(), %s)
        """, (nombre, cantidad, empresa_id))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return redirect("/productos")


@app.route("/imprimir_codigo_barras/<int:producto_id>")
def imprimir_codigo_barras(producto_id):
    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nombre, codigo_barras
        FROM productos
        WHERE id = %s AND empresa_id = %s AND activo = TRUE
        LIMIT 1
    """, (producto_id, empresa_id))
    producto = cursor.fetchone()
    conn.close()

    if not producto or not producto["codigo_barras"]:
        return "El producto no tiene un código de barras válido.", 404

    return render_template("imprimir_codigo_barras.html", producto=producto)


@app.route("/codigo_barras/<codigo>")
def codigo_barras(codigo):
    try:
        clase = barcode.get_barcode_class("code128")
        codigo_barra = clase(codigo, writer=SVGWriter())
        contenido = codigo_barra.render({
            "module_width": 0.30, "module_height": 12,
            "font_size": 9, "text_distance": 4, "quiet_zone": 4
        })
        return Response(contenido, mimetype="image/svg+xml")
    except Exception:
        return "Código de barras inválido", 400


@app.route("/buscar_producto_codigo")
def buscar_producto_codigo():
    if "usuario" not in session:
        return {"ok": False}, 401

    codigo = request.args.get("codigo", "").strip()
    empresa_id = session["empresa_id"]
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nombre, codigo_barras,
               precio_mayorista, precio_individual,
               precio_mostrador, costo
        FROM productos
        WHERE codigo_barras = %s AND empresa_id = %s AND activo = TRUE
        LIMIT 1
    """, (codigo, empresa_id))
    producto = cursor.fetchone()
    conn.close()

    if not producto:
        return {"ok": False, "mensaje": "No existe un producto con ese código."}, 404

    return {"ok": True, "producto": dict(producto)}


@app.route("/eliminar_producto/<int:id>")
def eliminar_producto(id):

    if "usuario" not in session:
        return redirect("/")

    if session["rol"] == "vendedor":
        return redirect("/productos")
        

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

        nombre_producto = producto[0]

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

    return redirect("/productos")

from datetime import date

@app.route("/ventas")
def ventas():

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    conn = conectar()
    cursor = conn.cursor()

    # ================= VENTAS =================
    cursor.execute("""
        SELECT *
        FROM pedidos
        WHERE empresa_id = %s
        AND eliminado = 0
        ORDER BY id DESC
    """, (empresa_id,))

    ventas = [dict(v) for v in cursor.fetchall()]

    # ================= RESUMEN DIARIO =================
    cursor.execute("""
        SELECT 
            SUM(total) as facturado,
            SUM(abono) as abonado,
            SUM(total - abono) as deben
        FROM facturas
        WHERE empresa_id = %s
        AND fecha::date = CURRENT_DATE
    """, (empresa_id,))

    dia = cursor.fetchone()
    dia = dict(dia) if dia else {
        "facturado": 0,
        "abonado": 0,
        "deben": 0
    }

    # ================= RESUMEN MENSUAL =================
    cursor.execute("""
        SELECT 
            SUM(total) as facturado,
            SUM(abono) as abonado,
            SUM(total - abono) as deben
        FROM facturas
        WHERE empresa_id = %s
        AND TO_CHAR(fecha::timestamp, 'YYYY-MM') = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
    """, (empresa_id,))

    mes = cursor.fetchone()
    mes = dict(mes) if mes else {
        "facturado": 0,
        "abonado": 0,
        "deben": 0
    }

    # ================= HISTÓRICO DIARIO =================
    cursor.execute("""
        SELECT 
            fecha::date as dia,
            SUM(total) as facturado,
            SUM(abono) as abonado,
            SUM(total - abono) as deben
        FROM facturas
        WHERE empresa_id = %s
        GROUP BY dia
        ORDER BY dia DESC
    """, (empresa_id,))

    diario = [dict(r) for r in cursor.fetchall()]

    # ================= HISTÓRICO MENSUAL =================
    cursor.execute("""
        SELECT 
            TO_CHAR(fecha::timestamp, 'YYYY-MM') as mes,
            SUM(total) as facturado,
            SUM(abono) as abonado,
            SUM(total - abono) as deben
        FROM facturas
        WHERE empresa_id = %s
        GROUP BY mes
        ORDER BY mes DESC
    """, (empresa_id,))

    mensual = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return render_template(
        "ventas.html",
        ventas=ventas,
        dia=dia,
        mes=mes,
        diario=diario,
        mensual=mensual
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

    # Total vendido
    cursor.execute("""
        SELECT SUM(precio) as total
        FROM pedidos
        WHERE empresa_id = %s
        AND eliminado = 0
    """, (empresa_id,))

    total = cursor.fetchone()["total"] or 0

    # Total pedidos
    cursor.execute("""
        SELECT COUNT(*) as total_pedidos
        FROM pedidos
        WHERE empresa_id = %s
        AND eliminado = 0
    """, (empresa_id,))

    total_pedidos = cursor.fetchone()["total_pedidos"]

    # Producto mas vendido
    cursor.execute("""
        SELECT producto, COUNT(*) as total
        FROM pedidos
        WHERE empresa_id = %s
        GROUP BY producto
        ORDER BY total DESC
        LIMIT 1
    """, (empresa_id,))

    top_producto = cursor.fetchone()

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

    # =========================
    # FILTROS
    # =========================
    filtro = request.args.get("filtro", "pendientes")

    buscar = request.args.get(
        "buscar",
        ""
    ).strip().lower()

    fecha = request.args.get("fecha", "")

    domiciliario = request.args.get(
        "domiciliario",
        ""
    ).strip().lower()

    # =========================
    # CONEXIÓN
    # =========================
    conn = conectar()
    cursor = conn.cursor()

    # =========================
    # QUERY BASE
    # =========================
    query = """
        SELECT *
        FROM pedidos
        WHERE empresa_id = %s
    """

    params = [empresa_id]

    # =========================
    # FILTRO ESTADO
    # =========================
    if filtro == "pendientes":

        query += """
            AND estado = 'pendiente'
            AND eliminado = 0
        """

    elif filtro == "entregados":

        query += """
            AND estado = 'entregado'
            AND eliminado = 0
        """

    elif filtro == "eliminados":

        query += """
            AND eliminado = 1
        """

    elif filtro == "todos":

        query += """
            AND eliminado = 0
        """

    # =========================
    # BUSCADOR CLIENTE/PRODUCTO
    # =========================
    if buscar:

        query += """
            AND (
                LOWER(cliente) LIKE %s
                OR LOWER(producto) LIKE %s
            )
        """

        params.append(f"%{buscar}%")
        params.append(f"%{buscar}%")

    # =========================
    # FILTRO FECHA
    # =========================
    if fecha:

        query += """
            AND fecha::date = %s
        """

        params.append(fecha)

    # =========================
    # FILTRO DOMICILIARIO
    # =========================
    if domiciliario:

        query += """
            AND LOWER(
                COALESCE(domiciliario, '')
            ) LIKE %s
        """

        params.append(f"%{domiciliario}%")

    # =========================
    # ORDEN
    # =========================
    query += " ORDER BY id DESC"

    # =========================
    # DEBUG
    # =========================
    print("QUERY:", query)
    print("PARAMS:", params)

    # =========================
    # EJECUTAR
    # =========================
    cursor.execute(query, params)

    pedidos = cursor.fetchall()

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

    # =========================
    # FILTROS
    # =========================
    factura_filtro = request.args.get("factura", "").strip()
    cliente_filtro = request.args.get("cliente", "").strip()
    estado = request.args.get("estado", "").strip().lower()
    fecha = request.args.get("fecha", "").strip()

    facturas = obtener_facturas(empresa_id)

    facturas = [dict(f) for f in facturas]

    # =========================
    # TOTALES GLOBALES
    # =========================
    total_facturado = 0
    total_abonado = 0
    total_deben = 0

    # =========================
    # CALCULAR SALDO REAL
    # =========================
    for f in facturas:

        total = f["total"] or 0
        abono = f["abono"] or 0

        saldo = total - abono
        f["saldo"] = saldo

        total_facturado += total
        total_abonado += abono

        if saldo > 0:
            total_deben += saldo

        if saldo <= 0:
            f["estado_calculado"] = "pagado"
        elif abono > 0:
            f["estado_calculado"] = "parcial"
        else:
            f["estado_calculado"] = "pendiente"

    # =========================
    # FILTRO NÚMERO DE FACTURA
    # =========================
    if factura_filtro:
        facturas = [
            f for f in facturas
            if str(f["id"]) == factura_filtro
        ]

    # =========================
    # FILTRO CLIENTE
    # =========================
    if cliente_filtro:
        facturas = [
            f for f in facturas
            if cliente_filtro.lower() in str(f["cliente"] or "").lower()
        ]

    # =========================
    # FILTRO FECHA
    # =========================
    if fecha:
        facturas = [
            f for f in facturas
            if f["fecha"] and str(f["fecha"]).startswith(fecha)
        ]

    # =========================
    # FILTRO ESTADO
    # =========================
    if estado:
        facturas = [
            f for f in facturas
            if f["estado_calculado"] == estado
        ]

    # =========================
    # MOSTRAR CARTERA
    # =========================
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
    observacion = request.form.get("observacion", "")

    if not factura_id or not abono:
        return "Datos incompletos", 400

    registrar_abono(
        factura_id=int(factura_id),
        abono=float(abono),
        observacion=observacion,
        empresa_id=session["empresa_id"]
    )

    return redirect("/cartera")

@app.route("/abonar_factura/<int:factura_id>", methods=["POST"])
def abonar_factura(factura_id):

    if "usuario" not in session:
        return redirect("/")

    empresa_id = session["empresa_id"]

    abono_nuevo = float(request.form["abono"])
    observacion = request.form.get("observacion", "")

    conn = conectar()
    cursor = conn.cursor()

    # 🔎 traer factura
    cursor.execute("""
        SELECT * FROM facturas
        WHERE id=%s AND empresa_id=%s
    """, (factura_id, empresa_id))

    factura = cursor.fetchone()

    if not factura:
        return "Factura no existe"

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
        SET abono=%s, estado=%s
        WHERE id=%s AND empresa_id=%s
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
        VALUES (%s, %s, %s, datetime('now'), %s, %s)
    """, (
        factura_id,
        factura["cliente"],
        abono_nuevo,
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
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM recibos_abono
        WHERE id=%s
        AND empresa_id=%s
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
@app.route("/editar_cliente/<int:id>")
def editar_cliente(id):

    if "usuario" not in session:
        return redirect("/")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM clientes
        WHERE id = %s
        AND empresa_id = %s
    """, (id, session["empresa_id"]))

    cliente = cursor.fetchone()
    conn.close()

    return render_template("editar_cliente.html", cliente=cliente)
@app.route("/actualizar_cliente/<int:id>", methods=["POST"])
def actualizar_cliente(id):

    if "usuario" not in session:
        return redirect("/")

    nombre = request.form.get("nombre")
    direccion = request.form.get("direccion")
    ciudad = request.form.get("ciudad")
    telefono = request.form.get("telefono")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE clientes
        SET nombre=%s,
            direccion=%s,
            ciudad=%s,
            telefono=%s
        WHERE id=%s
    """, (nombre, direccion, ciudad, telefono, id))

    conn.commit()
    conn.close()

    flash("✅ Cliente actualizado correctamente", "success")

    return redirect("/clientes")

# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

