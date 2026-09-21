import os
import psycopg2
from psycopg2.extras import DictCursor
import bcrypt
import sys
from datetime import datetime

# PostgreSQL: Railway proporciona DATABASE_URL automáticamente.
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "No se encontró DATABASE_URL. Configura la variable de entorno con la URL de PostgreSQL."
    )

DB = DATABASE_URL

def conectar():
    return psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)


def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS empresas (
        id SERIAL PRIMARY KEY,
        nombre TEXT UNIQUE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        usuario TEXT UNIQUE,
        password TEXT,
        rol TEXT NOT NULL DEFAULT 'vendedor',
        empresa_id INTEGER
    )
    """)
    

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id SERIAL PRIMARY KEY,
        nombre TEXT,
        precio_mayorista REAL,
        precio_individual REAL,
        precio_mostrador REAL,
        costo REAL,
        codigo_barras TEXT,
        empresa_id INTEGER,
        activo INTEGER DEFAULT 1
    )
    """)

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

        precio REAL DEFAULT 0,
        abono REAL DEFAULT 0,

        tipo_precio TEXT,

        estado TEXT DEFAULT 'pendiente',
        eliminado INTEGER DEFAULT 0,

        fecha TEXT,
        fecha_entrega TEXT,

        empresa_id INTEGER
    );
    """)
    
        # =========================
    # FACTURAS
    # =========================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facturas (
        id SERIAL PRIMARY KEY,
        cliente TEXT,
        direccion TEXT,
        ciudad TEXT,
        telefono TEXT,
        fecha TEXT,
        total REAL,
        abono REAL DEFAULT 0,
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
        precio_unitario REAL,
        subtotal REAL,
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
        codigo_barras TEXT,
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
        fecha TEXT,
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
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS creditos (
        id SERIAL PRIMARY KEY,
        cliente TEXT,
        factura_id INTEGER,
        total REAL,
        abonado REAL DEFAULT 0,
        saldo REAL,
        estado TEXT,
        plazo_pago TEXT,
        fecha TEXT,
        empresa_id INTEGER
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pagos_credito (
        id SERIAL PRIMARY KEY,
        factura_id INTEGER,
        cliente TEXT,
        abono REAL,
        fecha TEXT,
        observacion TEXT,
        empresa_id INTEGER
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recibos_abono (
        id SERIAL PRIMARY KEY,
        factura_id INTEGER,
        cliente TEXT,
        valor_abono REAL,
        saldo_anterior REAL,
        saldo_nuevo REAL,
        fecha TEXT,
        empresa_id INTEGER
    )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM empresas") 
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO empresas (nombre) VALUES ('Mi Empresa')")
        cursor.execute("INSERT INTO empresas (nombre) VALUES ('Empresa Demo')")
        print("🔥 DB inicializada")

    # 🔥 ESTO FALTABA
    conn.commit()
    conn.close()


from datetime import datetime, timezone, timedelta
import pytz

def ahora():
    bogota = timezone(timedelta(hours=-5))
    return datetime.now(bogota).strftime("%Y-%m-%d %H:%M:%S")

def crear_usuario(usuario, password, rol, empresa_id):
   

    conn = conectar()
    cursor = conn.cursor()

    # verificar si existe
    cursor.execute("""
        SELECT id FROM usuarios WHERE usuario = %s AND empresa_id = %s
    """, (usuario, empresa_id))

    if cursor.fetchone():
        return False  # ya existe

    # hash password
    hash_password = bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    cursor.execute("""
        INSERT INTO usuarios (usuario, password, rol, empresa_id)
        VALUES (%s, %s, %s, %s)
    """, (usuario, hash_password, rol, empresa_id))

    conn.commit()
    conn.close()

    return True
    
def validar_usuario(usuario, password):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, usuario, password, rol, empresa_id
        FROM usuarios
        WHERE usuario = %s
    """, (usuario,))

    resultado = cursor.fetchone()

    conn.close()

    if resultado is None:
        return None

    # Verificar contraseña
    if not bcrypt.checkpw(
        password.encode("utf-8"),
        resultado["password"].encode("utf-8")
    ):
        return None

    return resultado

def crear_cliente(nombre, direccion, ciudad, telefono,
                  tipo_id, identificacion, empresa_id):

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

def obtener_clientes(empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM clientes
        WHERE empresa_id = %s
        ORDER BY nombre ASC
    """, (empresa_id,))

    data = cursor.fetchall()

    conn.close()

    return data

def obtener_empresas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre FROM empresas")
    data = cursor.fetchall()

    conn.close()
    return data

def obtener_productos(empresa_id):
    

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM productos
        WHERE empresa_id = %s
        AND activo=1           
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
    domiciliario, cantidad,
    precio, abono, tipo_precio, empresa_id
):

    conn = conectar()
    cursor = conn.cursor()

    from datetime import datetime
    from db import ahora
    fecha = ahora()

    cursor.execute("""
        INSERT INTO pedidos (
            cliente,
            producto,
            direccion,
            ciudad,
            telefono,
            domiciliario,
            cantidad,
            precio,
            abono,
            tipo_precio,
            fecha,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        cliente,
        producto,
        direccion,
        ciudad,
        telefono,
        domiciliario,
        cantidad,
        precio,
        abono,
        tipo_precio,
        fecha,
        empresa_id
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


def obtener_pedidos_eliminados(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM pedidos
        WHERE empresa_id = %s
        AND eliminado = 1
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()
    conn.close()
    return data

def cambiar_estado(id, estado):
    conn = conectar()
    cursor = conn.cursor()

    from datetime import datetime
    from db import ahora
    if estado == "entregado":
        fecha_entrega = ahora()
    else:
        fecha_entrega = None

    cursor.execute("""
        UPDATE pedidos
        SET estado=%s, fecha_entrega=%s
        WHERE id=%s
    """, (estado, fecha_entrega, id))

    conn.commit()
    conn.close()


def eliminar_pedido(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE pedidos
        SET eliminado=1
        WHERE id=%s
    """, (id,))

    conn.commit()
    conn.close()

def recuperar_pedido(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE pedidos
        SET eliminado=0
        WHERE id=%s
    """, (id,))

    conn.commit()
    conn.close()

from db import ahora

def total_ventas_dia(empresa_id):
    """Total facturado hoy para la empresa actual."""
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(total), 0) AS total
        FROM facturas
        WHERE DATE(fecha::timestamp) = CURRENT_DATE
          AND empresa_id = %s
    """, (empresa_id,))

    total = cursor.fetchone()["total"] or 0
    conn.close()
    return total


def total_ventas_mes(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(total), 0) AS total
        FROM facturas
        WHERE TO_CHAR(fecha::timestamp, 'YYYY-MM') = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
          AND empresa_id = %s
    """, (empresa_id,))

    total = cursor.fetchone()["total"] or 0
    conn.close()
    return total


def facturas_emitidas_hoy(empresa_id):
    """Cantidad de facturas emitidas hoy para la empresa actual."""
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM facturas
        WHERE DATE(fecha::timestamp) = CURRENT_DATE
          AND empresa_id = %s
    """, (empresa_id,))

    total = cursor.fetchone()["total"] or 0
    conn.close()
    return total


def saldo_cartera(empresa_id):
    """Saldo pendiente de cartera de la empresa actual."""
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(saldo), 0) AS total
        FROM creditos
        WHERE empresa_id = %s
          AND COALESCE(saldo, 0) > 0
    """, (empresa_id,))

    total = cursor.fetchone()["total"] or 0
    conn.close()
    return total


def productos_top_5_mes(empresa_id):
    """Devuelve los 5 productos con más unidades vendidas en el mes actual."""
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            d.producto,
            COALESCE(SUM(d.cantidad), 0) AS total
        FROM detalle_factura d
        INNER JOIN facturas f ON f.id = d.factura_id
        WHERE f.empresa_id = %s
          AND TO_CHAR(f.fecha::timestamp, 'YYYY-MM') = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
        GROUP BY d.producto
        ORDER BY total DESC, d.producto ASC
        LIMIT 5
    """, (empresa_id,))

    data = cursor.fetchall()
    conn.close()
    return data


def producto_top_mes(empresa_id):
    """Compatibilidad: devuelve únicamente el producto número 1."""
    data = productos_top_5_mes(empresa_id)
    return data[0] if data else None

def crear_factura(
    cliente,
    direccion,
    ciudad,
    telefono,
    empresa_id,
    productos,
    tipo_precio,
    tipo_venta,
    plazo_pago=None,
    abono=0,
    domiciliario=""
):

    import os
    from datetime import datetime
    from db import ahora
    conn = conectar()
    cursor = conn.cursor()

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total = 0

    # =========================
    # NORMALIZAR ABONO
    # =========================
    try:
        abono = float(abono)
    except:
        abono = 0

    # =========================
    # CALCULAR TOTAL FACTURA
    # =========================
    for p in productos:

        precio = float(p.get("precio") or 0)
        cantidad = int(p.get("cantidad") or 0)

        # Facturación por UNIDADES: el precio es por unidad.
        subtotal = precio * cantidad
        total += subtotal

    saldo = total - abono
    if saldo < 0:
        saldo = 0

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
            plazo_pago,
            abono,
            domiciliario,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        plazo_pago,
        abono,
        domiciliario,
        empresa_id
    ))

    factura_id = cursor.fetchone()[0]

    # =========================
    # DETALLE FACTURA
    # =========================
    for p in productos:

        precio = float(p.get("precio") or 0)
        cantidad = int(p.get("cantidad") or 0)
        # Facturación por unidades: el precio es por unidad.
        subtotal = precio * cantidad

        cursor.execute("""
            INSERT INTO detalle_factura (
                factura_id,
                producto,
                cantidad,
                precio_unitario,
                subtotal
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            factura_id,
            p.get("producto"),
            cantidad,
            precio,
            subtotal
        ))

        # =========================
        # DESCONTAR INVENTARIO
        # =========================

        cursor.execute("""
            SELECT stock_unidades
            FROM inventario
            WHERE producto=%s AND empresa_id=%s
        """, (p.get("producto"), empresa_id))

        inv = cursor.fetchone()

        if inv:
            nuevas_unidades = max(
                inv["stock_unidades"] - int(p.get("cantidad") or 0), 0
            )

            cursor.execute("""
                UPDATE inventario
                SET stock_unidades=%s
                WHERE producto=%s AND empresa_id=%s
            """, (
                nuevas_unidades,
                p.get("producto"),
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
    import os

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
    import os

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

def registrar_compra(producto, cantidad, empresa_id, codigo_barras=None):
    conn = conectar()
    cursor = conn.cursor()
    fecha = ahora()
    codigo_barras = (codigo_barras or "").strip()

    if codigo_barras:
        cursor.execute("""
            SELECT nombre, codigo_barras
            FROM productos
            WHERE codigo_barras = %s AND empresa_id = %s AND activo = 1
            LIMIT 1
        """, (codigo_barras, empresa_id))
        encontrado = cursor.fetchone()
        if encontrado:
            producto = encontrado["nombre"]
            codigo_barras = encontrado["codigo_barras"]

    cursor.execute("""
        SELECT id FROM inventario
        WHERE producto = %s AND empresa_id = %s
    """, (producto, empresa_id))
    existe = cursor.fetchone()

    if existe:
        cursor.execute("""
            UPDATE inventario
            SET stock_unidades = stock_unidades + %s,
                codigo_barras = COALESCE(NULLIF(%s, ''), codigo_barras)
            WHERE producto = %s AND empresa_id = %s
        """, (cantidad, codigo_barras, producto, empresa_id))
    else:
        if not codigo_barras:
            cursor.execute("""
                SELECT codigo_barras
                FROM productos
                WHERE nombre = %s AND empresa_id = %s AND activo = 1
                LIMIT 1
            """, (producto, empresa_id))
            fila = cursor.fetchone()
            codigo_barras = fila["codigo_barras"] if fila else None

        cursor.execute("""
            INSERT INTO inventario (producto, stock_unidades, codigo_barras, empresa_id)
            VALUES (%s, %s, %s, %s)
        """, (producto, cantidad, codigo_barras, empresa_id))

    cursor.execute("""
        INSERT INTO movimientos_inventario
            (producto, tipo, cantidad, fecha, empresa_id)
        VALUES (%s, 'entrada', %s, %s, %s)
    """, (producto, cantidad, fecha, empresa_id))

    conn.commit()
    conn.close()

def obtener_inventario(empresa_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT producto, stock_unidades, codigo_barras
        FROM inventario
        WHERE empresa_id = %s
        ORDER BY producto ASC
    """, (empresa_id,))
    data = cursor.fetchall()
    conn.close()
    return data

def obtener_facturas(empresa_id):
    import os

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM facturas
        WHERE empresa_id = %s
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()

    conn.close()
    return data

def crear_factura_empresa(empresa_id):
    from datetime import datetime
    import os
    from db import ahora

    conn = conectar()
    cursor = conn.cursor()

    fecha = ahora()

    # 🔥 obtener pedidos pendientes
    cursor.execute("""
        SELECT * FROM pedidos
        WHERE empresa_id = %s AND estado = 'pendiente' AND eliminado = 0
    """, (empresa_id,))

    pedidos = cursor.fetchall()

    if not pedidos:
        conn.close()
        return None

    total = 0

    # 🔥 crear factura
    cursor.execute("""
        INSERT INTO facturas (cliente, fecha, total, empresa_id)
        VALUES (%s, %s, 0, %s)
        RETURNING id
    """, ("FACTURA EMPRESA", fecha, empresa_id))

    factura_id = cursor.fetchone()[0]

    for p in pedidos:

        precio_unitario = obtener_precio_producto(p["producto"], empresa_id)

        subtotal = precio_unitario * p["cantidad"]

        total += subtotal

        cursor.execute("""
            INSERT INTO detalle_factura (factura_id, producto, cantidad, precio_unitario, subtotal)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            factura_id,
            p["producto"],
            p["cantidad"],
            precio_unitario,
            subtotal
        ))

        # 🔥 marcar como entregado o facturado
        cursor.execute("""
            UPDATE pedidos
            SET estado = 'entregado'
            WHERE id = %s
        """, (p["id"],))

    cursor.execute("UPDATE facturas SET total=%s WHERE id=%s", (total, factura_id))

    conn.commit()
    conn.close()

    return factura_id

def crear_pedido_desde_factura(
    factura_id,
    cliente,
    producto,
    direccion,
    ciudad,
    telefono,
    domiciliario,
    cantidad,
    empresa_id,
    tipo_precio
):

    import os

    conn = conectar()
    cursor = conn.cursor()

    # 🔥 obtener precio correcto
    precio_unitario = obtener_precio_producto(
        producto,
        empresa_id,
        tipo_precio
    )

    # Calcular total por unidades.
    total = precio_unitario * cantidad

    cursor.execute("""
        INSERT INTO pedidos (
            factura_id,
            cliente,
            producto,
            direccion,
            ciudad,
            telefono,
            domiciliario,
            cantidad,
            precio,
            empresa_id,
            estado,
            eliminado
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pendiente', 0)
    """, (
        factura_id,
        cliente,
        producto,
        direccion,
        ciudad,
        telefono,
        domiciliario,
        cantidad,
        total,
        empresa_id
    ))

    conn.commit()
    conn.close()

def descontar_inventario(producto, cantidad, empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    # 🔥 restar unidades
    cursor.execute("""
        UPDATE inventario
        SET stock_unidades = stock_unidades - %s
        WHERE producto = %s AND empresa_id = %s
    """, (cantidad, producto, empresa_id))

    conn.commit()
    conn.close()

def crear_credito(cliente, factura_id, total, empresa_id):

    conn = conectar()
    cursor = conn.cursor()
    from db import ahora
    fecha = ahora()

    cursor.execute("""
        INSERT INTO creditos (
            cliente,
            factura_id,
            total,
            saldo,
            fecha,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        cliente,
        factura_id,
        total,
        total,
        fecha,
        empresa_id
    ))

    conn.commit()
    conn.close()

def abonar_credito(credito_id, valor):

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT saldo, abonado FROM creditos WHERE id=%s
    """, (credito_id,))

    c = cursor.fetchone()

    nuevo_abono = c["abonado"] + valor
    nuevo_saldo = c["saldo"] - valor

    estado = "pagado" if nuevo_saldo <= 0 else "pendiente"

    cursor.execute("""
        UPDATE creditos
        SET abonado=%s, saldo=%s, estado=%s
        WHERE id=%s
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
        SELECT * FROM creditos
        WHERE empresa_id=%s
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()

    conn.close()
    return data

def registrar_abono(factura_id, abono, observacion, empresa_id):

    import os
    from datetime import datetime

    conn = conectar()
    cursor = conn.cursor()

    # =========================
    # FACTURA
    # =========================
    cursor.execute("""
        SELECT *
        FROM facturas
        WHERE id=%s
        AND empresa_id=%s
    """, (factura_id, empresa_id))

    factura = cursor.fetchone()

    if not factura:
        conn.close()
        return

    nuevo_abono = (factura["abono"] or 0) + abono

    saldo = factura["total"] - nuevo_abono

    saldo_anterior = factura["total"] - (factura["abono"] or 0)

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
    # ACTUALIZAR FACTURA
    # =========================
    cursor.execute("""
        UPDATE facturas
        SET abono=%s,
            estado=%s
        WHERE id=%s
    """, (
        nuevo_abono,
        estado,
        factura_id
    ))

    # =========================
    # ACTUALIZAR CREDITO
    # =========================
    cursor.execute("""
        UPDATE creditos
        SET abonado=%s,
            saldo=%s,
            estado=%s
        WHERE factura_id=%s
    """, (
        nuevo_abono,
        saldo,
        estado,
        factura_id
    ))

    # =========================
    # HISTORIAL
    # =========================
    from db import ahora
    fecha = ahora()

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
        abono,
        fecha,
        observacion,
        empresa_id
    ))

    # =========================
    # RECIBO DE ABONO
    # =========================
    cursor.execute("""
        INSERT INTO recibos_abono (
            factura_id,
            cliente,
            valor_abono,
            saldo_anterior,
            saldo_nuevo,
            fecha,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        factura_id,
        factura["cliente"],
        abono,
        saldo_anterior,
        saldo,
        fecha,
        empresa_id
    ))

    recibo_id = cursor.fetchone()[0]

    conn.commit()
    conn.close()

    return recibo_id

def obtener_historial_abonos(factura_id, empresa_id):

    import os

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM pagos_credito
        WHERE factura_id=%s
        AND empresa_id=%s
        ORDER BY id DESC
    """, (
        factura_id,
        empresa_id
    ))

    pagos = cursor.fetchall()

    conn.close()

    return pagos
