import pytz
import os
import psycopg2
import psycopg2.extras
import bcrypt
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

UTC = timezone.utc
COLOMBIA = pytz.timezone("America/Bogota")

# 🔥 SIEMPRE guardar en base de datos (UTC)
def ahora_utc():
    return datetime.now(UTC)


# 🔥 CONVERTIR SOLO PARA MOSTRAR EN FRONTEND
def a_colombia(dt):
    if dt is None:
        return None

    # si viene naive (sin timezone), asumimos UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    return dt.astimezone(COLOMBIA)


# 🔥 (OPCIONAL PERO MUY ÚTIL)
# formateo directo para templates
def formatear_colombia(dt):
    dt_col = a_colombia(dt)
    if not dt_col:
        return ""
    return dt_col.strftime("%Y-%m-%d %H:%M")

DATABASE_URL = os.environ.get("DATABASE_URL")
print("DATABASE_URL:", DATABASE_URL)

def conectar():
    DATABASE_URL = os.environ.get("DATABASE_URL")

    if not DATABASE_URL:
        raise Exception("DATABASE_URL no configurada en Railway")

    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )

    # 🔥 FORZAR ZONA HORARIA DE SESIÓN
    cursor = conn.cursor()
    cursor.execute("SET TIME ZONE 'UTC'")
    cursor.close()

    return conn

def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()

    # =========================
    # EMPRESAS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id SERIAL PRIMARY KEY,
            nombre TEXT UNIQUE
        )
    """)

    # =========================
    # USUARIOS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            usuario TEXT UNIQUE,
            password TEXT,
            rol TEXT NOT NULL DEFAULT 'vendedor',
            empresa_id INTEGER
        )
    """)

    # =========================
    # PRODUCTOS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            precio_mayorista DOUBLE PRECISION,
            precio_individual DOUBLE PRECISION,
            precio_mostrador DOUBLE PRECISION,
            costo DOUBLE PRECISION,
            empresa_id INTEGER,
            activo BOOLEAN DEFAULT TRUE
        )
    """)

    # =========================
    # PEDIDOS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id SERIAL PRIMARY KEY,
            cliente TEXT,
            producto TEXT,
            direccion TEXT,
            ciudad TEXT,
            telefono TEXT,
            domiciliario TEXT,
            cantidad INTEGER,
            peso DOUBLE PRECISION,
            precio DOUBLE PRECISION DEFAULT 0,
            abono DOUBLE PRECISION DEFAULT 0,
            tipo_precio TEXT,
            estado TEXT DEFAULT 'pendiente',
            eliminado INTEGER DEFAULT 0,
            fecha TIMESTAMPTZ,
            fecha_entrega TIMESTAMPTZ,
            empresa_id INTEGER
        )
    """)

    # =========================_
    # FACTURAS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facturas (
            id SERIAL PRIMARY KEY,
            cliente TEXT,
            direccion TEXT,
            ciudad TEXT,
            telefono TEXT,
            fecha TIMESTAMPTZ,
            total DOUBLE PRECISION,
            abono DOUBLE PRECISION DEFAULT 0,
            estado TEXT,
            tipo_venta TEXT,
            plazo_pago TEXT,
            domiciliario TEXT,
            tipo_precio TEXT,
            empresa_id INTEGER
        )
    """)

    # =========================
    # DETALLE FACTURA
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detalle_factura (
            id SERIAL PRIMARY KEY,
            factura_id INTEGER,
            producto TEXT,
            cantidad INTEGER,
            peso DOUBLE PRECISION,
            precio_unitario DOUBLE PRECISION,
            subtotal DOUBLE PRECISION,
            tipo_precio TEXT
        )
    """)

    # =========================
    # INVENTARIO
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario (
            id SERIAL PRIMARY KEY,
            producto TEXT,
            stock_unidades INTEGER DEFAULT 0,
            stock_kilos DOUBLE PRECISION DEFAULT 0,
            empresa_id INTEGER
        )
    """)

    # =========================
    # MOVIMIENTOS INVENTARIO
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos_inventario (
            id SERIAL PRIMARY KEY,
            producto TEXT,
            tipo TEXT,
            cantidad INTEGER,
            peso DOUBLE PRECISION,
            fecha TIMESTAMPTZ,
            empresa_id INTEGER
        )
    """)

    # =========================
    # MENSAJEROS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mensajeros (
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            telefono TEXT,
            empresa_id INTEGER
        )
    """)

    # =========================
    # CLIENTES
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            direccion TEXT,
            ciudad TEXT,
            telefono TEXT,
            tipo_id TEXT,
            identificacion TEXT,
            empresa_id INTEGER
        )
    """)

    # =========================
    # CREDITOS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS creditos (
            id SERIAL PRIMARY KEY,
            cliente TEXT,
            factura_id INTEGER,
            total DOUBLE PRECISION,
            abonado DOUBLE PRECISION DEFAULT 0,
            saldo DOUBLE PRECISION,
            estado TEXT,
            plazo_pago TEXT,
            fecha TIMESTAMPTZ,
            empresa_id INTEGER
        )
    """)

    # =========================
    # PAGOS CREDITO
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagos_credito (
            id SERIAL PRIMARY KEY,
            factura_id INTEGER,
            cliente TEXT,
            abono DOUBLE PRECISION,
            fecha TIMESTAMPTZ,
            observacion TEXT,
            empresa_id INTEGER
        )
    """)

    # =========================
    # RECIBOS ABONO
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recibos_abono (
            id SERIAL PRIMARY KEY,
            factura_id INTEGER,
            cliente TEXT,
            valor_abono DOUBLE PRECISION,
            saldo_anterior DOUBLE PRECISION,
            saldo_nuevo DOUBLE PRECISION,
            fecha TIMESTAMPTZ,
            empresa_id INTEGER
        )
    """)

    # =========================
    # DATOS INICIALES
    # =========================
    cursor.execute("SELECT COUNT(*) FROM empresas")
    count = cursor.fetchone()["count"]

    if count == 0:
        cursor.execute("INSERT INTO empresas (nombre) VALUES (%s)", ("Mi Empresa",))
        cursor.execute("INSERT INTO empresas (nombre) VALUES (%s)", ("Empresa Demo",))
        print("🔥 DB inicializada")

    conn.commit()
    conn.close()



import bcrypt

def crear_usuario(usuario, password, rol, empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    # =========================
    # VERIFICAR SI EXISTE
    # =========================
    cursor.execute("""
        SELECT id
        FROM usuarios
        WHERE usuario = %s AND empresa_id = %s
    """, (usuario, empresa_id))

    if cursor.fetchone():
        conn.close()
        return False

    # =========================
    # HASH PASSWORD
    # =========================
    hash_password = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")  # importante en Postgres

    # =========================
    # INSERT USUARIO
    # =========================
    cursor.execute("""
        INSERT INTO usuarios (usuario, password, rol, empresa_id)
        VALUES (%s, %s, %s, %s)
    """, (usuario, hash_password, rol, empresa_id))

    conn.commit()
    conn.close()

    return True
    



# =========================
# VALIDAR USUARIO
# =========================
def validar_usuario(usuario, password, empresa_id):
    conn = conectar()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT id, usuario, password, rol, empresa_id
        FROM usuarios
        WHERE usuario = %s AND empresa_id = %s
    """, (usuario, empresa_id))

    user = cursor.fetchone()
    conn.close()

    if not user:
        return None

    password_bd = user["password"]

    if bcrypt.checkpw(password.encode("utf-8"), password_bd.encode("utf-8")):
        return user

    return None


# =========================
# CREAR CLIENTE
# =========================
def crear_cliente(nombre, direccion, ciudad, telefono, tipo_id, identificacion, empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO clientes (
            nombre,
            direccion,
            ciudad,
            telefono,
            tipo_id,
            identificacion,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        nombre,
        direccion,
        ciudad,
        telefono,
        tipo_id,
        identificacion,
        empresa_id
    ))

    conn.commit()
    conn.close()


# =========================
# OBTENER CLIENTES
# =========================
def obtener_clientes(empresa_id):

    conn = conectar()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT *
        FROM clientes
        WHERE empresa_id = %s
        ORDER BY id DESC
    """, (empresa_id,))

    clientes = cursor.fetchall()

    conn.close()
    return clientes


# =========================
# OBTENER EMPRESAS
# =========================
def obtener_empresas():
    conn = conectar()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT id, nombre
        FROM empresas
    """)

    data = cursor.fetchall()

    conn.close()
    return data

# =========================
# OBTENER PRODUCTOS
# =========================
def obtener_productos(empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM productos
        WHERE empresa_id = %s
        AND activo = TRUE
    """, (empresa_id,))

    productos = cursor.fetchall()

    conn.close()
    return productos

def obtener_precio_producto(nombre, empresa_id, tipo_precio):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT precio_mayorista,
            precio_individual,
            precio_mostrador
        FROM productos
        WHERE nombre=%s AND empresa_id=%s
    """, (nombre, empresa_id))

    p = cursor.fetchone()
    conn.close()

    if not p:
        return 0

    if tipo_precio == "mayorista":
        return p["precio_mayorista"]

    elif tipo_precio == "individual":
        return p["precio_individual"]

    elif tipo_precio == "mostrador":
        return p["precio_mostrador"]

    # fallback seguro
    return p["precio_individual"]
    
def obtener_costo_producto(nombre_producto, empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT costo
        FROM productos
        WHERE nombre = %s AND empresa_id = %s
    """, (nombre_producto, empresa_id))

    resultado = cursor.fetchone()

    conn.close()

    if resultado:
        return resultado["costo"]

    return 0

def obtener_pedidos(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            id,
            cliente,
            producto,
            direccion,
            ciudad,
            telefono,
            domiciliario,
            cantidad,
            peso,
            precio,
            fecha,
            fecha_entrega,  
            estado,
            eliminado
        FROM pedidos
        WHERE empresa_id = %s
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()
    conn.close()
    return data


def agregar_pedido(
    cliente, producto, direccion, ciudad, telefono,
    domiciliario, cantidad, peso,
    precio, abono, tipo_precio, empresa_id
):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO pedidos (
            cliente, producto, direccion, ciudad, telefono,
            domiciliario, cantidad, peso,
            precio, abono, tipo_precio, empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        cliente, producto, direccion, ciudad, telefono,
        domiciliario, cantidad, peso,
        precio, abono, tipo_precio, empresa_id
    ))

    conn.commit()
    conn.close()

def obtener_pedidos_pendientes(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM pedidos
        WHERE empresa_id = %s
        AND estado = 'pendiente'
        AND eliminado = 0
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()
    conn.close()
    return data


def obtener_pedidos_entregados(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM pedidos
        WHERE empresa_id = %s
        AND estado = 'entregado'
        AND eliminado = 0
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()
    conn.close()
    return data


# =========================
# PEDIDOS ELIMINADOS
# =========================
def obtener_pedidos_eliminados(empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM pedidos
        WHERE empresa_id = %s
        AND eliminado = 1
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()
    conn.close()
    return data


# =========================
# CAMBIAR ESTADO
# =========================
def cambiar_estado(id, estado):

    conn = conectar()
    cursor = conn.cursor()

    if estado == "entregado":
        fecha_entrega = ahora_utc()
    else:
        fecha_entrega = None

    cursor.execute("""
        UPDATE pedidos
        SET estado = %s,
            fecha_entrega = %s
        WHERE id = %s
    """, (estado, fecha_entrega, id))

    conn.commit()
    conn.close()


# =========================
# ELIMINAR PEDIDO (SOFT DELETE)
# =========================
def eliminar_pedido(id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE pedidos
        SET eliminado = 1
        WHERE id = %s
    """, (id,))

    conn.commit()
    conn.close()


# =========================
# RECUPERAR PEDIDO
# =========================
def recuperar_pedido(id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE pedidos
        SET eliminado = 0
        WHERE id = %s
    """, (id,))

    conn.commit()
    conn.close()


# =========================
# VENTAS DEL DÍA
# =========================
def total_ventas_dia(empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(total), 0) AS total
        FROM facturas
        WHERE empresa_id = %s
        AND (fecha AT TIME ZONE 'America/Bogota')::date =
            (NOW() AT TIME ZONE 'America/Bogota')::date
    """, (empresa_id,))

    total = cursor.fetchone()["total"]
    conn.close()
    return total


# =========================
# VENTAS DEL MES
# =========================
def total_ventas_mes(empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(total), 0) AS total
        FROM facturas
        WHERE empresa_id = %s
        AND DATE_TRUNC('month', fecha AT TIME ZONE 'America/Bogota')
            = DATE_TRUNC('month', NOW() AT TIME ZONE 'America/Bogota')
    """, (empresa_id,))

    total = cursor.fetchone()["total"]
    conn.close()
    return total


# =========================
# PRODUCTO TOP DEL MES
# =========================
def producto_top_mes(empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT producto, SUM(cantidad) AS total
        FROM detalle_factura df
        JOIN facturas f ON f.id = df.factura_id
        WHERE f.empresa_id = %s
        AND DATE_TRUNC('month', f.fecha AT TIME ZONE 'America/Bogota')
            = DATE_TRUNC('month', NOW() AT TIME ZONE 'America/Bogota')
        GROUP BY producto
        ORDER BY total DESC
        LIMIT 1
    """, (empresa_id,))

    return cursor.fetchone()



def crear_factura(
    cliente,
    direccion,
    ciudad,
    telefono,
    empresa_id,
    productos,
    tipo_precio,
    tipo_venta,
    forma_pago,
    plazo_pago=None,
    abono=0,
    domiciliario=""
):

    conn = conectar()
    cursor = conn.cursor()

    fecha = ahora_utc()

    total = 0

    # =========================
    # NORMALIZAR ABONO
    # =========================
    try:
        abono = float(abono or 0)
    except:
        abono = 0

    # =========================
    # CALCULAR TOTAL
    # =========================
    for p in productos:

        producto = p.get("producto")

        tipo_precio_item = p.get("tipo_precio") or tipo_precio

        precio = float(
            obtener_precio_producto(
                producto,
                empresa_id,
                tipo_precio_item
            ) or 0
        )

        peso = float(p.get("peso") or 0)

        subtotal = precio * peso
        total += subtotal

    # =========================
    # ABONO / SALDO
    # =========================
    abono = min(abono, total)
    saldo = total - abono

    # =========================
    # ESTADO
    # =========================
    if tipo_venta == "credito":
        if abono <= 0:
            estado = "pendiente"
        elif saldo == 0:
            estado = "pagado"
        else:
            estado = "parcial"
    else:
        estado = "pagado"
        abono = total
        saldo = 0

    # =========================
    # INSERT FACTURA
    # =========================
    cursor.execute("""
        INSERT INTO facturas (
            cliente,
            direccion,
            ciudad,
            telefono,
            fecha,
            total,
            estado,
            tipo_precio,
            tipo_venta,
            forma_pago,
            plazo_pago,
            abono,
            domiciliario,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        cliente,
        direccion,
        ciudad,
        telefono,
        fecha,
        total,
        estado,
        tipo_precio,
        tipo_venta,
        forma_pago,
        plazo_pago,
        abono,
        domiciliario,
        empresa_id
    ))

    factura_id = cursor.fetchone()["id"]

    # =========================
    # DETALLE FACTURA
    # =========================
    for p in productos:

        producto = p.get("producto")
        cantidad = int(p.get("cantidad") or 0)
        peso = float(p.get("peso") or 0)

        precio = float(
            obtener_precio_producto(
                producto,
                empresa_id,
                tipo_precio
            ) or 0
        )

        subtotal = precio * peso

        # =========================
        # GUARDAR DETALLE
        # =========================
        cursor.execute("""
            INSERT INTO detalle_factura (
                factura_id,
                producto,
                cantidad,
                peso,
                precio_unitario,
                subtotal
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            factura_id,
            producto,
            cantidad,
            peso,
            precio,
            subtotal
        ))

        # =========================
        # VALIDAR INVENTARIO
        # =========================
        cursor.execute("""
            SELECT stock_unidades, stock_kilos
            FROM inventario
            WHERE producto = %s
            AND empresa_id = %s
        """, (
            producto,
            empresa_id
        ))

        stock = cursor.fetchone()

        if stock:

            stock_unidades = float(stock["stock_unidades"] or 0)
            stock_kilos = float(stock["stock_kilos"] or 0)

            if stock_unidades < cantidad:
                conn.rollback()
                conn.close()
                return {
                    "error": f"No hay suficientes unidades de {producto}"
                }

            if stock_kilos < peso:
                conn.rollback()
                conn.close()
                return {
                    "error": f"No hay suficientes kilos de {producto}"
                }   

        # =========================
        # DESCONTAR INVENTARIO
        # =========================
        cursor.execute("""
            UPDATE inventario
            SET
                stock_unidades = stock_unidades - %s,
                stock_kilos = stock_kilos - %s
            WHERE producto = %s
            AND empresa_id = %s
        """, (
            cantidad,
            peso,
            producto,
            empresa_id
        ))

    # =========================
    # CARTERA (CRÉDITO)
    # =========================
    if tipo_venta == "credito":

        cursor.execute("""
            INSERT INTO creditos (
                cliente,
                factura_id,
                total,
                abonado,
                saldo,
                estado,
                plazo_pago,
                fecha,
                empresa_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            cliente,
            factura_id,
            total,
            abono,
            saldo,
            estado,
            plazo_pago,
            fecha,
            empresa_id
        ))

    conn.commit()
    conn.close()

    return factura_id

def obtener_factura(factura_id, empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM facturas
        WHERE id = %s AND empresa_id = %s
    """, (factura_id, empresa_id))

    factura = cursor.fetchone()

    conn.close()
    return factura


def obtener_detalles_factura(factura_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM detalle_factura
        WHERE factura_id = %s
    """, (factura_id,))

    detalles = cursor.fetchall()

    conn.close()
    return detalles


def registrar_compra(producto, cantidad, peso, empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM inventario
        WHERE producto = %s AND empresa_id = %s
    """, (producto, empresa_id))

    existe = cursor.fetchone()

    if existe:
        cursor.execute("""
            UPDATE inventario
            SET stock_unidades = stock_unidades + %s,
                stock_kilos = stock_kilos + %s
            WHERE producto = %s AND empresa_id = %s
        """, (cantidad, peso, producto, empresa_id))

    else:
        cursor.execute("""
            INSERT INTO inventario (producto, stock_unidades, stock_kilos, empresa_id)
            VALUES (%s, %s, %s, %s)
        """, (producto, cantidad, peso, empresa_id))

    conn.commit()
    conn.close()


def obtener_inventario(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT producto, stock_unidades, stock_kilos
        FROM inventario
        WHERE empresa_id = %s
    """, (empresa_id,))

    data = cursor.fetchall()

    conn.close()
    return data


def obtener_facturas(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            *,
            TO_CHAR(
                fecha AT TIME ZONE 'America/Bogota',
                'YYYY-MM-DD HH24:MI'
            ) AS fecha_formateada
        FROM facturas
        WHERE empresa_id = %s
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()

    conn.close()
    return data

def crear_factura_empresa(empresa_id):

    conn = conectar()

    # 🔥 IMPORTANTE
    cursor = conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    )

    # =====================================================
    # OBTENER PEDIDOS PENDIENTES
    # =====================================================
    cursor.execute("""
        SELECT *
        FROM pedidos
        WHERE empresa_id = %s
        AND estado = 'pendiente'
        AND eliminado = 0
    """, (empresa_id,))

    pedidos = cursor.fetchall()

    if not pedidos:
        conn.close()
        return None

    total = 0

    # =====================================================
    # FECHA UTC REAL
    # =====================================================
    fecha = ahora_utc()

    # =====================================================
    # CREAR FACTURA VACÍA
    # =====================================================
    cursor.execute("""
        INSERT INTO facturas (
            cliente,
            fecha,
            total,
            abono,
            estado,
            tipo_venta,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        "FACTURA EMPRESA",
        fecha,
        0,
        0,
        "pendiente",
        "contado",
        empresa_id
    ))

    factura_id = cursor.fetchone()["id"]

    # =====================================================
    # DETALLES FACTURA
    # =====================================================
    for p in pedidos:

        precio_unitario = float(
            obtener_precio_producto(
                p["producto"],
                empresa_id,
                p.get("tipo_precio", "individual")
            ) or 0
        )

        cantidad = int(p.get("cantidad") or 0)
        peso = float(p.get("peso") or 0)

        subtotal = precio_unitario * peso

        total += subtotal

        # =========================================
        # INSERT DETALLE
        # =========================================
        cursor.execute("""
            INSERT INTO detalle_factura (
                factura_id,
                producto,
                cantidad,
                peso,
                precio_unitario,
                subtotal
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            factura_id,
            p["producto"],
            cantidad,
            peso,
            precio_unitario,
            subtotal
        ))

        # =========================================
        # MARCAR PEDIDO ENTREGADO
        # =========================================
        cursor.execute("""
            UPDATE pedidos
            SET estado = 'entregado',
                fecha_entrega = %s
            WHERE id = %s
        """, (
            fecha,
            p["id"]
        ))

    # =====================================================
    # ACTUALIZAR TOTAL FACTURA
    # =====================================================
    cursor.execute("""
        UPDATE facturas
        SET total = %s,
            abono = %s,
            estado = %s
        WHERE id = %s
    """, (
        total,
        total,
        "pagado",
        factura_id
    ))

    conn.commit()
    conn.close()

    return factura_id

def descontar_inventario(producto, cantidad, peso, empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    # 🔥 restar unidades
    cursor.execute("""
        UPDATE inventario
        SET stock_unidades = stock_unidades - %s
        WHERE producto = %s AND empresa_id = %s
    """, (cantidad, producto, empresa_id))

    # 🔥 restar kilos
    cursor.execute("""
        UPDATE inventario
        SET stock_kilos = stock_kilos - %s
        WHERE producto = %s AND empresa_id = %s
    """, (peso, producto, empresa_id))

    conn.commit()
    conn.close()


def crear_credito(cliente, factura_id, total, empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    fecha = ahora_utc()

    cursor.execute("""
        INSERT INTO creditos (
            cliente,
            factura_id,
            total,
            abonado,
            saldo,
            fecha,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        cliente,
        factura_id,
        total,
        0,      # abonado inicia en 0 (IMPORTANTE)
        total,  # saldo inicial
        fecha,
        empresa_id
    ))

    conn.commit()
    conn.close()


def abonar_credito(credito_id, valor):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT saldo, abonado
        FROM creditos
        WHERE id = %s
    """, (credito_id,))

    c = cursor.fetchone()

    if not c:
        conn.close()
        return

    actual_abonado = float(c["abonado"] or 0)
    actual_saldo = float(c["saldo"] or 0)
    valor = float(valor)

    nuevo_abono = actual_abonado + valor
    nuevo_saldo = actual_saldo - valor

    estado = "pagado" if nuevo_saldo <= 0 else "pendiente"

    cursor.execute("""
        UPDATE creditos
        SET abonado = %s,
            saldo = %s,
            estado = %s
        WHERE id = %s
    """, (
        nuevo_abono,
        nuevo_saldo,
        estado,
        credito_id
    ))

    conn.commit()
    conn.close()


def obtener_creditos(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM creditos
        WHERE empresa_id = %s
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()

    conn.close()
    return data

def registrar_abono(
    factura_id,
    abono,
    observacion,
    forma_pago,
    empresa_id
):

    conn = conectar()
    cursor = conn.cursor()

    # =========================
    # FACTURA
    # =========================

    cursor.execute("""
        SELECT id, cliente, total, abono
        FROM facturas
        WHERE id = %s
        AND empresa_id = %s
    """, (factura_id, empresa_id))

    factura = cursor.fetchone()

    if not factura:
        conn.close()
        return None

    actual_abono = factura["abono"] or 0
    nuevo_abono = actual_abono + abono

    saldo_anterior = factura["total"] - actual_abono
    saldo = factura["total"] - nuevo_abono

    # =========================
    # ESTADO
    # =========================

    if saldo <= 0:
        estado = "pagado"
        saldo = 0
    elif nuevo_abono > 0:
        estado = "parcial"
    else:
        estado = "pendiente"

    # =========================
    # UPDATE FACTURA
    # =========================

    cursor.execute("""
        UPDATE facturas
        SET abono = %s,
            estado = %s
        WHERE id = %s
        AND empresa_id = %s
    """, (
        nuevo_abono,
        estado,
        factura_id,
        empresa_id
    ))

    # =========================
    # UPDATE CREDITO
    # =========================

    cursor.execute("""
        UPDATE creditos
        SET abonado = %s,
            saldo = %s,
            estado = %s
        WHERE factura_id = %s
        AND empresa_id = %s
    """, (
        nuevo_abono,
        saldo,
        estado,
        factura_id,
        empresa_id
    ))

    # =========================
    # FECHA CENTRALIZADA (UTC)
    # =========================

    fecha = ahora_utc()

    # =========================
    # HISTORIAL PAGOS
    # =========================

    cursor.execute("""
        INSERT INTO pagos_credito (
            factura_id,
            cliente,
            abono,
            fecha,
            observacion,
            forma_pago,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        factura_id,
        factura["cliente"],
        abono,
        fecha,
        observacion,
        forma_pago,
        empresa_id
    ))

    # =========================
    # RECIBO
    # =========================

    cursor.execute("""
        INSERT INTO recibos_abono (
            factura_id,
            cliente,
            valor_abono,
            saldo_anterior,
            saldo_nuevo,
            fecha,
            forma_pago,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        factura_id,
        factura["cliente"],
        abono,
        saldo_anterior,
        saldo,
        fecha,
        forma_pago,
        empresa_id
    ))

    conn.commit()

    cursor.execute("""
        SELECT id
        FROM recibos_abono
        WHERE factura_id = %s
        ORDER BY id DESC
        LIMIT 1
    """, (factura_id,))

    recibo_id = cursor.fetchone()["id"]

    conn.close()

    return recibo_id

def obtener_historial_abonos(factura_id, empresa_id):

    conn = conectar()
    cursor = conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    )

    cursor.execute("""
        SELECT
            *,
            TO_CHAR(
                fecha AT TIME ZONE 'America/Bogota',
                'YYYY-MM-DD HH24:MI'
            ) AS fecha
        FROM pagos_credito
        WHERE factura_id = %s
        AND empresa_id = %s
        ORDER BY pagos_credito.fecha DESC
    """, (
        factura_id,
        empresa_id
    ))

    pagos = cursor.fetchall()

    conn.close()

    return pagos

def validar_factura(data):
    tipo = data.get("tipo")  # credito o contado

    campos_obligatorios = [
        "cliente",
        "direccion",
        "ciudad",
        "telefono",
        "tipo_id",
        "identificacion",
        "domiciliario"   # 👈 AQUI
    ]

    # -------------------------
    # VALIDACIÓN BASE (texto)
    # -------------------------
    for campo in campos_obligatorios:
        valor = data.get(campo)

        if valor is None or str(valor).strip() == "":
            return False, f"El campo {campo} es obligatorio"

    # -------------------------
    # VALIDACIÓN PRODUCTOS
    # -------------------------
    productos = data.get("producto", [])
    cantidades = data.get("cantidad", [])
    precios = data.get("precio", [])

    if not productos:
        return False, "Debe agregar al menos un producto"

    for i in range(len(productos)):
        try:
            if float(cantidades[i]) <= 0:
                return False, "Cantidad inválida (debe ser mayor a 0)"
        except:
            return False, "Cantidad inválida"

        try:
            if float(precios[i]) <= 0:
                return False, "Precio inválido (debe ser mayor a 0)"
        except:
            return False, "Precio inválido"

    # -------------------------
    # VALIDACIÓN DOMICILIARIO (OPCIONAL)
    # -------------------------
    domiciliario = data.get("domiciliario", "")
    if domiciliario is None:
        domiciliario = ""

    # -------------------------
    # CRÉDITO
    # -------------------------
    if tipo == "credito":

        abono = data.get("abono")

        if abono is None or str(abono).strip() == "":
            abono = 0

        try:
            abono = float(abono)
        except:
            return False, "Abono inválido"

        if abono < 0:
            return False, "El abono no puede ser negativo"

    # -------------------------
    # CONTADO
    # -------------------------
    elif tipo == "contado":

        # puede venir vacío → lo dejamos en 0
        abono = data.get("abono")

        if abono is None or str(abono).strip() == "":
            abono = 0

        try:
            abono = float(abono)
        except:
            return False, "Abono inválido"

        # opcional: no negativo
        if abono < 0:
            return False, "El abono no puede ser negativo"

    else:
        return False, "Tipo de factura inválido"

    return True, "OK"

#guadar cambios railway y git 
#git add .
#git commit -m "fix: migrate fully to postgres"
#git push origin main
