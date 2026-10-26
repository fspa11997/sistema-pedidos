import pytz
import os
import hmac
import secrets
import gzip
import psycopg2
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
    obtener_metricas_dashboard,
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
    registrar_abono,
    METODOS_PAGO,
    segundos_bloqueo_login,
    registrar_fallo_login,
    limpiar_intentos_login
)



from db import inicializar_db
def seed():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:

        import bcrypt

        # La clave inicial viene de SUPERADMIN_PASSWORD; si no existe se genera
        # una aleatoria que se imprime una sola vez en los logs.
        clave_inicial = os.environ.get("SUPERADMIN_PASSWORD")
        if not clave_inicial:
            clave_inicial = secrets.token_urlsafe(12)
            print(f"🔑 Clave inicial de superadmin (cámbiala): {clave_inicial}")

        hash_password = bcrypt.hashpw(
            clave_inicial.encode(),
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

# Caché de recursos estáticos: evita volver a descargar CSS, JS e imágenes
# que no han cambiado al navegar entre módulos.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400

@app.after_request
def optimizar_respuesta(response):
    """Reduce el tiempo de transferencia sin modificar el contenido visible."""
    content_type = response.headers.get("Content-Type", "")
    content_length = response.headers.get("Content-Length")
    aceptado = "gzip" in request.headers.get("Accept-Encoding", "").lower()

    if (aceptado and response.status_code == 200 and
            not response.direct_passthrough and
            not response.is_streamed and
            "Content-Encoding" not in response.headers and
            content_length and int(content_length) >= 500 and
            (content_type.startswith("text/html") or
             content_type.startswith("text/css") or
             content_type.startswith("application/javascript") or
             content_type.startswith("text/javascript"))):
        response.set_data(gzip.compress(response.get_data(), compresslevel=5))
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Vary"] = "Accept-Encoding"
        response.headers.pop("Content-Length", None)

    return response


def formato_fecha_hora(valor):
    """Convierte fechas UTC a hora de Colombia y las muestra DD/MM/AAAA HH:MM.

    Railway/PostgreSQL suele entregar timestamps sin zona como UTC; por eso,
    los valores naive se interpretan como UTC antes de convertirlos a Bogotá.
    """
    if valor is None or valor == "":
        return "-"
    try:
        if isinstance(valor, datetime):
            fecha = valor
        else:
            texto = str(valor).strip()
            fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = pytz.UTC.localize(fecha)
        fecha = fecha.astimezone(zona_colombia)
        return fecha.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError, OverflowError):
        for patron in ("%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                fecha = datetime.strptime(str(valor).strip(), patron)
                fecha = pytz.UTC.localize(fecha).astimezone(zona_colombia)
                return fecha.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                continue
    return str(valor)


app.jinja_env.filters["fecha_hora"] = formato_fecha_hora


def formato_fecha_pedido(valor):
    """Pedidos: las fechas naive se guardan como hora local de Colombia."""
    if valor is None or valor == "":
        return "-"
    try:
        if isinstance(valor, datetime):
            fecha = valor
        else:
            texto = str(valor).strip()
            fecha = datetime.fromisoformat(texto.replace("Z", "+05:00"))
        if fecha.tzinfo is None:
            fecha = zona_colombia.localize(fecha)
        else:
            fecha = fecha.astimezone(zona_colombia)
        return fecha.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError, OverflowError):
        return str(valor)


app.jinja_env.filters["fecha_pedido"] = formato_fecha_pedido

_secret = os.environ.get("SECRET_KEY")
if not _secret:
    raise RuntimeError(
        "Falta la variable de entorno SECRET_KEY. Genera una con: "
        "python -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.secret_key = _secret
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("RAILWAY_ENVIRONMENT"))


# =========================
# PROTECCIÓN CSRF
# =========================
def generar_csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = generar_csrf_token


@app.before_request
def verificar_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        enviado = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        esperado = session.get("_csrf", "")
        if not esperado or not hmac.compare_digest(esperado, enviado):
            return "Sesión expirada o solicitud no válida. Recarga la página e inténtalo de nuevo.", 403

zona_colombia = pytz.timezone("America/Bogota")
fecha_entrega = datetime.now(zona_colombia)
ROLES_PERMITIDOS = {"admin", "vendedor"}
PASSWORD_MIN = 8


def error_password(password):
    """Devuelve un mensaje si la contraseña no cumple la política, o None."""
    if len(password) < PASSWORD_MIN:
        return f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres."
    if len(password.encode("utf-8")) > 72:
        return "La contraseña es demasiado larga (máximo 72 bytes)."
    if password.isdigit() or password.isalpha():
        return "La contraseña debe combinar letras y números."
    return None


def ip_cliente():
    # Railway agrega la IP real al final de X-Forwarded-For; el resto lo
    # puede escribir el cliente, así que se toma el último valor.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.remote_addr or "desconocida"


# =========================
# LOGIN
# =========================
@app.route("/", methods=["GET", "POST"])
def login():
    empresas = obtener_empresas()
    
    if request.method == "POST":
        user = request.form["usuario"]
        pwd = request.form["password"]

        clave_intentos = f"{user.strip().lower()[:100]}|{ip_cliente()}"
        espera = segundos_bloqueo_login(clave_intentos)
        if espera:
            minutos = (espera + 59) // 60
            return render_template(
                "login.html", empresas=empresas,
                error=f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} min."
            ), 429

        usuario = validar_usuario(user, pwd)

        if usuario:
            limpiar_intentos_login(clave_intentos)

            session["usuario"] = usuario["usuario"]
            session["rol"] = usuario["rol"]
            session["empresa_id"] = usuario["empresa_id"]

            return redirect("/dashboard")

        registrar_fallo_login(clave_intentos)
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
    empresas = obtener_empresas(conn=conn)

    buscar = request.args.get("buscar", "")
    fecha = request.args.get("fecha")
    domiciliario_filtro = request.args.get("domiciliario", "")
    
    metricas = obtener_metricas_dashboard(empresa_id, conn=conn)
    total_dia = metricas["total_dia"] or 0
    total_mes = metricas["total_mes"] or 0
    facturas_hoy = metricas["facturas_hoy"] or 0
    cartera_pendiente = metricas["cartera_pendiente"] or 0

    top_5_productos = productos_top_5_mes(empresa_id, conn=conn)
    top_producto = top_5_productos[0] if top_5_productos else None

    filtro = request.args.get("filtro", "todos")

    if filtro == "pendientes":
        pedidos = obtener_pedidos_pendientes(empresa_id, conn=conn)
    elif filtro == "entregados":
        pedidos = obtener_pedidos_entregados(empresa_id, conn=conn)
    elif filtro == "eliminados":
        pedidos = obtener_pedidos_eliminados(empresa_id, conn=conn)
    else:
        pedidos = obtener_pedidos(empresa_id, conn=conn)

    productos = obtener_productos(empresa_id, conn=conn)
    clientes = obtener_clientes(empresa_id, conn=conn)
    inventario = obtener_inventario(empresa_id, conn=conn)

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

@app.route("/entregar/<int:id>", methods=["POST"])
def entregar(id):
    if "usuario" not in session:
        return redirect("/")
    cambiar_estado(id, "entregado", session["empresa_id"])
    return redirect("/pedidos")


@app.route("/recuperar/<int:id>", methods=["POST"])
def recuperar(id):
    if "usuario" not in session:
        return redirect("/")
    recuperar_pedido(id, session["empresa_id"])
    return redirect("/pedidos")


@app.route("/crear_usuario", methods=["POST"])
def crear_usuario():

    if "rol" not in session or session["rol"] != "owner_global":
        return "No autorizado", 403

    usuario = request.form["usuario"].strip()
    password = request.form["password"]
    rol = request.form["rol"]

    if not usuario or len(usuario) > 100:
        flash("⚠️ El nombre de usuario es obligatorio (máximo 100 caracteres).", "error")
        return redirect("/dashboard")

    if rol not in ROLES_PERMITIDOS:
        flash("⚠️ Rol no válido.", "error")
        return redirect("/dashboard")

    try:
        empresa_id = int(request.form["empresa_id"])
    except (KeyError, ValueError):
        flash("⚠️ Empresa no válida.", "error")
        return redirect("/dashboard")

    problema = error_password(password)
    if problema:
        flash("⚠️ " + problema, "error")
        return redirect("/dashboard")

    import bcrypt
    
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM empresas WHERE id = %s", (empresa_id,))
    if not cursor.fetchone():
        conn.close()
        flash("⚠️ La empresa seleccionada no existe.", "error")
        return redirect("/dashboard")

    # 🔍 VERIFICAR SI YA EXISTE
    cursor.execute("""
        SELECT id FROM usuarios WHERE usuario = %s
    """, (usuario,))

    existe = cursor.fetchone()

    if existe:
        conn.close()
        flash("⚠️ El usuario ya existe.", "error")
        return redirect("/dashboard")

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

    problema = error_password(nueva_password)
    if problema:
        flash("⚠️ " + problema, "error")
        return redirect("/dashboard")

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
@app.route("/eliminar_empresa/<int:id>", methods=["POST"])
def eliminar_empresa(id):

    if "rol" not in session or session["rol"] != "owner_global":
        return "No autorizado", 403

    conn = conectar()
    cursor = conn.cursor()

    # 🔴 BORRAR PRIMERO DATOS RELACIONADOS
    # detalle_factura no tiene empresa_id: se borra a través de sus facturas
    cursor.execute("""
        DELETE FROM detalle_factura
        WHERE factura_id IN (SELECT id FROM facturas WHERE empresa_id=%s)
    """, (id,))
    for tabla in (
        "recibos_abono", "pagos_credito", "creditos", "facturas",
        "movimientos_inventario", "inventario", "mensajeros", "clientes",
        "usuarios", "pedidos", "productos",
    ):
        cursor.execute(f"DELETE FROM {tabla} WHERE empresa_id=%s", (id,))

    # 🔥 BORRAR EMPRESA
    cursor.execute("DELETE FROM empresas WHERE id=%s", (id,))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

# =========================
# CAMBIAR ESTADO
# =========================
@app.route("/estado/<int:id>", methods=["POST"])
def estado(id):
    if "usuario" not in session:
        return redirect("/")

    cambiar_estado(id, "entregado", session["empresa_id"])
    return redirect("/dashboard")


# =========================
# ELIMINAR
# =========================
@app.route("/eliminar/<int:id>", methods=["POST"])
def eliminar(id):
    if "usuario" not in session:
        return redirect("/")

    eliminar_pedido(id, session["empresa_id"])
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
    metodo_pago = request.form.get("metodo_pago", "").strip().lower()

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

    if abono < 0:
        flash("⚠️ El abono no puede ser negativo", "error")
        return redirect("/dashboard")

    # =========================
    # MÉTODO DE PAGO
    # =========================
    # Obligatorio en ventas de contado y en crédito con abono inicial.
    if tipo_venta != "credito" or abono > 0:
        if metodo_pago not in METODOS_PAGO:
            flash("⚠️ Selecciona el método de pago (efectivo, tarjeta o nequi)", "error")
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
        domiciliario=domiciliario,
        metodo_pago=metodo_pago,
        usuario=session.get("usuario")
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
    productos = obtener_productos(empresa_id, )
    return render_template("productos.html", productos=productos)


@app.route("/producto_foto/<int:producto_id>")
def producto_foto(producto_id):
    if "usuario" not in session:
        return "No autorizado", 401
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT foto, foto_mimetype FROM productos WHERE id=%s AND empresa_id=%s", (producto_id, session["empresa_id"]))
    fila = cursor.fetchone()
    conn.close()
    if not fila or not fila["foto"]:
        return "Sin foto", 404
    return Response(bytes(fila["foto"]), mimetype=fila["foto_mimetype"] or "image/jpeg", headers={"Cache-Control":"no-store"})

@app.route("/subir_foto_producto/<int:producto_id>", methods=["POST"])
def subir_foto_producto(producto_id):
    if "usuario" not in session:
        return redirect("/")
    archivo = request.files.get("foto")
    if not archivo or not archivo.filename:
        flash("Selecciona una imagen.", "error")
        return redirect("/inventario")
    tipos = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    datos = archivo.read(5 * 1024 * 1024 + 1)
    if archivo.mimetype not in tipos or len(datos) > 5 * 1024 * 1024:
        flash("Usa JPG, PNG, WEBP o GIF de máximo 5 MB.", "error")
        return redirect("/inventario")
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE productos SET foto=%s, foto_mimetype=%s WHERE id=%s AND empresa_id=%s", (psycopg2.Binary(datos), archivo.mimetype, producto_id, session["empresa_id"]))
    conn.commit()
    conn.close()
    return redirect("/inventario")

@app.route("/inventario")
def inventario_page():
    if "usuario" not in session:
        return redirect("/")
    empresa_id = session["empresa_id"]
    productos = obtener_productos(empresa_id)
    inventario = obtener_inventario(empresa_id)
    return render_template("inventario.html", productos=productos, inventario=inventario, fotos_por_nombre={p["nombre"]: p["id"] for p in productos})


@app.route("/producto/<int:producto_id>/foto", methods=["POST"])
def subir_foto_producto_nueva(producto_id):
    if "usuario" not in session:
        return redirect("/")#

    archivo = request.files.get("foto")
    if not archivo or not archivo.filename:
        return redirect("/inventario")

    permitidos = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if archivo.mimetype not in permitidos:
        return "Formato no permitido. Usa JPG, PNG, WEBP o GIF.", 400

    contenido = archivo.read(5 * 1024 * 1024 + 1)
    if not contenido:
        return "El archivo está vacío.", 400
    if len(contenido) > 5 * 1024 * 1024:
        return "La foto supera el máximo de 5 MB.", 400

    empresa_id = session["empresa_id"]
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE productos
            SET foto = %s, foto_mime = %s
            WHERE id = %s AND empresa_id = %s
        """, (psycopg2.Binary(contenido), archivo.mimetype, producto_id, empresa_id))
        if cursor.rowcount == 0:
            conn.rollback()
            return "Producto no encontrado.", 404
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return redirect("/inventario")


@app.route("/producto/<int:producto_id>/foto")
def ver_foto_producto(producto_id):
    if "usuario" not in session:
        return redirect("/")
    from io import BytesIO
    from flask import send_file
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT foto, foto_mime FROM productos
        WHERE id = %s AND empresa_id = %s
    """, (producto_id, session["empresa_id"]))
    fila = cursor.fetchone()
    conn.close()
    if not fila or not fila["foto"]:
        return "Foto no encontrada.", 404
    return send_file(BytesIO(bytes(fila["foto"])), mimetype=fila["foto_mime"] or "image/jpeg")


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
            WHERE codigo_barras = %s AND empresa_id = %s AND activo = 1
            LIMIT 1
        """, (codigo_barras, empresa_id))
        p = cursor.fetchone()
        conn.close()

        if not p:
            return render_template(
                "inventario.html",
                productos=obtener_productos(empresa_id),
                inventario=obtener_inventario(empresa_id),
                fotos_por_nombre={p["nombre"]: p["id"] for p in obtener_productos(empresa_id)},
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
        if not codigo or not codigo.strip():
            return "Código vacío", 400

        clase = barcode.get_barcode_class("code128")
        codigo_barra = clase(codigo, writer=SVGWriter())

        contenido = codigo_barra.render({
            "module_width": 0.30,
            "module_height": 15,
            "font_size": 10,
            "text_distance": 4,
            "quiet_zone": 4,
            "write_text": True
        })

        return Response(
            contenido,
            mimetype="image/svg+xml"
        )

    except Exception as e:
        app.logger.exception(
            "Error generando código de barras: %s", codigo
        )
        return f"Error generando código: {e}", 500

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


@app.route("/eliminar_producto/<int:id>", methods=["POST"])
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

@app.route("/ventas", methods=["GET", "POST"])
def ventas():
    if "usuario" not in session:
        return redirect("/")
    empresa_id = session.get("empresa_id")
    usuario = session.get("usuario", "")
    rol = session.get("rol", "vendedor")
    admin = rol in ("admin", "owner_global")
    conn = conectar(); cur = conn.cursor()
    mensaje = None
    try:
        if request.method == "POST":
            accion = request.form.get("accion", "")
            if accion in ("cuadrar", "cancelar_cuadre", "cerrar", "movimiento") and not admin:
                return "No autorizado", 403
            if accion == "movimiento":
                tipo = request.form.get("tipo")
                metodo = request.form.get("metodo_pago", "efectivo")
                concepto = request.form.get("concepto", "").strip()[:250]
                try: valor = round(float(request.form.get("valor", "0")), 2)
                except ValueError: valor = 0
                if tipo not in ("ingreso_manual", "egreso_manual") or metodo not in ("efectivo", "tarjeta", "nequi") or valor <= 0 or not concepto:
                    raise ValueError("Completa concepto, método y un valor mayor que cero.")
                cur.execute("SELECT id,estado FROM cajas WHERE empresa_id=%s AND estado IN ('abierta','en_cuadre') FOR UPDATE", (empresa_id,)); caja=cur.fetchone()
                if caja and caja['estado'] != 'abierta': raise ValueError("La caja está en cuadre; no admite movimientos.")
                if not caja:
                    cur.execute("INSERT INTO cajas(empresa_id,estado,base_inicial,abierta_por) VALUES (%s,'abierta',0,%s) RETURNING id",(empresa_id,usuario)); caja_id=cur.fetchone()[0]
                else: caja_id=caja['id']
                cur.execute("INSERT INTO movimientos_caja(caja_id,empresa_id,tipo,metodo_pago,valor,concepto,usuario,origen) VALUES (%s,%s,%s,%s,%s,%s,%s,'manual')",(caja_id,empresa_id,tipo,metodo,valor,concepto,usuario))
                conn.commit(); mensaje="Movimiento registrado."
            elif accion == "cuadrar":
                cur.execute("SELECT id,estado FROM cajas WHERE empresa_id=%s AND estado IN ('abierta','en_cuadre') FOR UPDATE",(empresa_id,)); caja=cur.fetchone()
                if not caja:
                    cur.execute("INSERT INTO cajas(empresa_id,estado,base_inicial,abierta_por) VALUES (%s,'abierta',0,%s) RETURNING id",(empresa_id,usuario)); caja={'id':cur.fetchone()[0],'estado':'abierta'}
                if caja['estado'] != 'abierta': raise ValueError("La caja ya está en cuadre.")
                cur.execute("UPDATE cajas SET estado='en_cuadre' WHERE id=%s",(caja['id'],))
                cur.execute("""SELECT metodo_pago, COALESCE(SUM(CASE WHEN tipo IN ('egreso_manual') THEN -valor WHEN tipo IN ('venta_contado','abono_inicial','abono_cartera','ingreso_manual') THEN valor ELSE 0 END),0) total FROM movimientos_caja WHERE caja_id=%s GROUP BY metodo_pago""",(caja['id'],))
                totals={r['metodo_pago']:float(r['total'] or 0) for r in cur.fetchall()}
                def num(k):
                    try: return round(float(request.form.get(k,0) or 0),2)
                    except ValueError: return 0
                cur.execute("INSERT INTO cuadres_caja(caja_id,empresa_id,usuario,esperado_efectivo,contado_efectivo,esperado_tarjeta,contado_tarjeta,esperado_nequi,contado_nequi,observacion) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (caja['id'],empresa_id,usuario,totals.get('efectivo',0),num('efectivo'),totals.get('tarjeta',0),num('tarjeta'),totals.get('nequi',0),num('nequi'),request.form.get('observacion','')[:500]))
                conn.commit(); mensaje="Cuadre guardado. La caja queda bloqueada hasta cerrar o cancelar el cuadre."
            elif accion == "cancelar_cuadre":
                cur.execute("SELECT id FROM cajas WHERE empresa_id=%s AND estado='en_cuadre' FOR UPDATE",(empresa_id,)); caja=cur.fetchone()
                if not caja: raise ValueError("No hay un cuadre activo para cancelar.")
                cur.execute("UPDATE cajas SET estado='abierta' WHERE id=%s",(caja['id'],)); cur.execute("UPDATE cuadres_caja SET estado='cancelado' WHERE caja_id=%s AND estado='vigente'",(caja['id'],)); conn.commit(); mensaje="Cuadre cancelado; la caja vuelve a estar habilitada."
            elif accion == "cerrar":
                cur.execute("SELECT * FROM cajas WHERE empresa_id=%s AND estado='en_cuadre' FOR UPDATE",(empresa_id,)); caja=cur.fetchone()
                if not caja: raise ValueError("Debes iniciar un cuadre antes del cierre.")
                cur.execute("SELECT * FROM cuadres_caja WHERE caja_id=%s AND estado='vigente' ORDER BY id DESC LIMIT 1",(caja['id'],)); cuadre=cur.fetchone()
                if not cuadre: raise ValueError("No se encontró el cuadre vigente.")
                diffs=[float(cuadre['contado_efectivo'] or 0)-float(cuadre['esperado_efectivo'] or 0),float(cuadre['contado_tarjeta'] or 0)-float(cuadre['esperado_tarjeta'] or 0),float(cuadre['contado_nequi'] or 0)-float(cuadre['esperado_nequi'] or 0)]
                obs=request.form.get('observacion','').strip()[:500]
                # La observación del cierre es opcional, incluso cuando existen diferencias.
                cur.execute("SELECT COALESCE(jsonb_agg(to_jsonb(m) ORDER BY m.id),'[]'::jsonb) snap FROM movimientos_caja m WHERE caja_id=%s",(caja['id'],)); snap=cur.fetchone()['snap']
                cur.execute("INSERT INTO cierres_caja(caja_id,empresa_id,usuario,total_efectivo,total_tarjeta,total_nequi,diferencia_efectivo,diferencia_tarjeta,diferencia_nequi,observacion,movimientos_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",(caja['id'],empresa_id,usuario,cuadre['contado_efectivo'],cuadre['contado_tarjeta'],cuadre['contado_nequi'],diffs[0],diffs[1],diffs[2],obs,__import__('json').dumps(snap, default=str)))
                cur.execute("UPDATE cuadres_caja SET estado='cerrado' WHERE id=%s",(cuadre['id'],))
                cur.execute("UPDATE cajas SET estado='cerrada',cerrada_en=(NOW() AT TIME ZONE 'America/Bogota'),cerrada_por=%s WHERE id=%s",(usuario,caja['id']))
                cur.execute("INSERT INTO cajas(empresa_id,estado,base_inicial,abierta_por) VALUES (%s,'abierta',0,%s)",(empresa_id,usuario))
                conn.commit(); mensaje="Cierre guardado. Se abrió una caja nueva con base cero."
            else: raise ValueError("Acción no válida.")
        cur.execute("SELECT * FROM cajas WHERE empresa_id=%s AND estado IN ('abierta','en_cuadre') ORDER BY id DESC LIMIT 1",(empresa_id,)); caja=cur.fetchone()
        if not caja:
            cur.execute("INSERT INTO cajas(empresa_id,estado,base_inicial,abierta_por) VALUES (%s,'abierta',0,%s) RETURNING *",(empresa_id,usuario)); caja=cur.fetchone(); conn.commit()
        cur.execute("SELECT * FROM movimientos_caja WHERE caja_id=%s ORDER BY id DESC",(caja['id'],)); movimientos=[dict(x) for x in cur.fetchall()]
        cur.execute("""SELECT metodo_pago, COALESCE(SUM(CASE WHEN tipo='egreso_manual' THEN -valor WHEN tipo IN ('venta_contado','abono_inicial','abono_cartera','ingreso_manual') THEN valor ELSE 0 END),0) total FROM movimientos_caja WHERE caja_id=%s GROUP BY metodo_pago""",(caja['id'],))
        totales={r['metodo_pago']:float(r['total'] or 0) for r in cur.fetchall()}
        desde=request.args.get('desde',''); hasta=request.args.get('hasta','')
        cur.execute("SELECT * FROM cuadres_caja WHERE empresa_id=%s AND (%s='' OR fecha::date >= NULLIF(%s,'')::date) AND (%s='' OR fecha::date <= NULLIF(%s,'')::date) ORDER BY id DESC LIMIT 200",(empresa_id,desde,desde,hasta,hasta)); cuadres=[dict(x) for x in cur.fetchall()]
        cur.execute("SELECT * FROM cierres_caja WHERE empresa_id=%s AND (%s='' OR fecha::date >= NULLIF(%s,'')::date) AND (%s='' OR fecha::date <= NULLIF(%s,'')::date) ORDER BY id DESC LIMIT 200",(empresa_id,desde,desde,hasta,hasta)); cierres=[dict(x) for x in cur.fetchall()]
        cur.execute("SELECT COALESCE(SUM(total),0) facturado, COALESCE(SUM(CASE WHEN tipo_venta='credito' THEN total-abono ELSE 0 END),0) saldo_credito FROM facturas WHERE empresa_id=%s AND fecha::date=(NOW() AT TIME ZONE 'America/Bogota')::date",(empresa_id,)); resumen=dict(cur.fetchone())
        cur.execute("SELECT id,estado,usuario,fecha,esperado_efectivo,contado_efectivo,esperado_tarjeta,contado_tarjeta,esperado_nequi,contado_nequi,observacion FROM cuadres_caja WHERE caja_id=%s AND estado='vigente' ORDER BY id DESC LIMIT 1",(caja['id'],)); cuadre_activo=cur.fetchone()
        return render_template('ventas.html', caja=dict(caja), movimientos=movimientos, totales=totales, cuadres=cuadres, cierres=cierres, desde=desde, hasta=hasta, resumen=dict(resumen), cuadre_activo=dict(cuadre_activo) if cuadre_activo else None, admin=admin, mensaje=mensaje)
    except ValueError as e:
        conn.rollback()
        cur.execute("SELECT * FROM cajas WHERE empresa_id=%s AND estado IN ('abierta','en_cuadre') ORDER BY id DESC LIMIT 1",(empresa_id,)); caja=cur.fetchone()
        cur.execute("SELECT * FROM movimientos_caja WHERE caja_id=%s ORDER BY id DESC",(caja['id'],)) if caja else None
        movimientos=[dict(x) for x in cur.fetchall()] if caja else []
        cur.execute("SELECT metodo_pago, COALESCE(SUM(CASE WHEN tipo='egreso_manual' THEN -valor WHEN tipo IN ('venta_contado','abono_inicial','abono_cartera','ingreso_manual') THEN valor ELSE 0 END),0) total FROM movimientos_caja WHERE caja_id=%s GROUP BY metodo_pago",(caja['id'],)) if caja else None
        totales={r['metodo_pago']:float(r['total'] or 0) for r in cur.fetchall()} if caja else {}
        return render_template('ventas.html', caja=dict(caja) if caja else {'estado':'abierta','id':'—'}, movimientos=movimientos, totales=totales, cuadres=[], cierres=[], desde='', hasta='', resumen={'facturado':0,'saldo_credito':0}, cuadre_activo=None, admin=admin, mensaje=str(e)), 400
    except Exception:
        conn.rollback()
        app.logger.exception("Error en el módulo Ventas/Caja para empresa_id=%s, acción=%s", empresa_id, request.form.get("accion", "GET"))
        return ("No se pudo completar la operación de Ventas/Caja. La operación fue cancelada para evitar registros parciales. Revisa los registros de Railway para ver el error SQL exacto.", 500)
    finally:
        conn.close()

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

    clientes = obtener_clientes(empresa_id, )

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

    factura_filtro = request.args.get("factura", "").strip()
    cliente_filtro = request.args.get("cliente", "").strip()
    estado = request.args.get("estado", "").strip().lower()
    fecha = request.args.get("fecha", "").strip()

    conn = conectar()
    cursor = conn.cursor()

    # Los totales generales se calculan en PostgreSQL, evitando descargar
    # todas las facturas para sumarlas en Python.
    cursor.execute("""
        SELECT
            COALESCE(SUM(total), 0) AS total_facturado,
            COALESCE(SUM(abono), 0) AS total_abonado,
            COALESCE(SUM(GREATEST(total - abono, 0)), 0) AS total_deben
        FROM facturas
        WHERE empresa_id = %s
    """, (empresa_id,))
    resumen = cursor.fetchone()

    query = """
        SELECT *,
               GREATEST(total - COALESCE(abono, 0), 0) AS saldo_calculado,
               CASE
                   WHEN GREATEST(total - COALESCE(abono, 0), 0) <= 0 THEN 'pagado'
                   WHEN COALESCE(abono, 0) > 0 THEN 'parcial'
                   ELSE 'pendiente'
               END AS estado_calculado
        FROM facturas
        WHERE empresa_id = %s
    """
    params = [empresa_id]

    if factura_filtro:
        query += " AND id = %s"
        try:
            params.append(int(factura_filtro))
        except ValueError:
            params.append(-1)

    if cliente_filtro:
        query += " AND LOWER(COALESCE(cliente, '')) LIKE %s"
        params.append(f"%{cliente_filtro.lower()}%")

    if fecha:
        # fecha se guarda en formato ISO; esta comparación aprovecha
        # el índice (empresa_id, fecha) y evita fecha::date.
        query += " AND fecha >= %s AND fecha < (%s::date + INTERVAL '1 day')::text"
        params.extend([fecha, fecha])

    if estado in ("pagado", "parcial", "pendiente"):
        if estado == "pagado":
            query += " AND GREATEST(total - COALESCE(abono, 0), 0) <= 0"
        elif estado == "parcial":
            query += " AND COALESCE(abono, 0) > 0 AND total > COALESCE(abono, 0)"
        else:
            query += " AND COALESCE(abono, 0) <= 0 AND total > 0"

    query += " ORDER BY id DESC"

    cursor.execute(query, params)
    facturas = cursor.fetchall()
    conn.close()

    # Mantener los nombres de las claves que ya usa la plantilla.
    facturas = [dict(f) for f in facturas]
    for f in facturas:
        f["saldo"] = f.get("saldo_calculado", 0) or 0
        f["estado_calculado"] = f.get("estado_calculado", "pendiente")

    return render_template(
        "cartera.html",
        facturas=facturas,
        total_facturado=resumen["total_facturado"] or 0,
        total_abonado=resumen["total_abonado"] or 0,
        total_deben=resumen["total_deben"] or 0
    )


@app.route("/abonar_credito", methods=["POST"])
def abonar_credito_route():

    if "usuario" not in session:
        return redirect("/")

    try:
        factura_id = int(request.form.get("factura_id", ""))
    except ValueError:
        flash("⚠️ Factura no válida.", "error")
        return redirect("/cartera")

    try:
        registrar_abono(
            factura_id=factura_id,
            abono=request.form.get("abono", ""),
            observacion=request.form.get("observacion", "")[:300],
            empresa_id=session["empresa_id"],
            metodo_pago=request.form.get("metodo_pago", ""),
            usuario=session.get("usuario")
        )
    except ValueError as e:
        flash("⚠️ " + str(e), "error")

    return redirect("/cartera")

@app.route("/abonar_factura/<int:factura_id>", methods=["POST"])
def abonar_factura(factura_id):

    if "usuario" not in session:
        return redirect("/")

    try:
        registrar_abono(
            factura_id=factura_id,
            abono=request.form.get("abono", ""),
            observacion=request.form.get("observacion", "")[:300],
            empresa_id=session["empresa_id"],
            metodo_pago=request.form.get("metodo_pago", "")
        )
    except ValueError as e:
        flash("⚠️ " + str(e), "error")

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
          AND empresa_id=%s
    """, (nombre, direccion, ciudad, telefono, id, session["empresa_id"]))

    conn.commit()
    conn.close()

    flash("✅ Cliente actualizado correctamente", "success")

    return redirect("/clientes")

# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

