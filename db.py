import os
import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.pool import ThreadedConnectionPool
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

# Métodos de pago aceptados (clave guardada en BD -> texto para mostrar)
METODOS_PAGO = {"efectivo": "Efectivo", "tarjeta": "Tarjeta", "nequi": "Nequi"}

# Pool de conexiones: evita abrir una conexión TCP nueva a PostgreSQL
# en cada consulta. Esto reduce bastante la latencia en Railway.
_POOL_MIN = 1
_POOL_MAX = 10
_pool = None

class _PooledConnection:
    """Pequeño adaptador para conservar conn.close() sin romper el código existente."""
    def __init__(self, raw_conn):
        self._raw_conn = raw_conn
        self._returned = False

    def cursor(self, *args, **kwargs):
        return self._raw_conn.cursor(*args, **kwargs)

    def commit(self):
        return self._raw_conn.commit()

    def rollback(self):
        return self._raw_conn.rollback()

    def close(self):
        if not self._returned:
            self._returned = True
            try:
                # Dejamos la conexión limpia antes de devolverla al pool.
                self._raw_conn.rollback()
            except Exception:
                pass
            _pool.putconn(self._raw_conn)

    def __getattr__(self, name):
        return getattr(self._raw_conn, name)


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            _POOL_MIN,
            _POOL_MAX,
            DATABASE_URL,
            cursor_factory=DictCursor,
            connect_timeout=10,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        )
    return _pool

def conectar():
    return _PooledConnection(_get_pool().getconn())


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
        activo INTEGER DEFAULT 1,
        foto BYTEA,
        foto_mimetype TEXT,
        iva_porcentaje NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (iva_porcentaje >= 0 AND iva_porcentaje <= 100)
    )
    """)

    cursor.execute("ALTER TABLE facturas ADD COLUMN IF NOT EXISTS metodo_pago TEXT")
    cursor.execute("ALTER TABLE pagos_credito ADD COLUMN IF NOT EXISTS metodo_pago TEXT")
    cursor.execute("ALTER TABLE recibos_abono ADD COLUMN IF NOT EXISTS metodo_pago TEXT")
    cursor.execute("ALTER TABLE productos ADD COLUMN IF NOT EXISTS foto BYTEA")
    cursor.execute("ALTER TABLE productos ADD COLUMN IF NOT EXISTS foto_mimetype TEXT")
    # IVA por producto y desglose tributario de las facturas (migración compatible con datos existentes).
    cursor.execute("ALTER TABLE productos ADD COLUMN IF NOT EXISTS iva_porcentaje NUMERIC(5,2) NOT NULL DEFAULT 0")


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
        subtotal REAL DEFAULT 0,
        iva_total REAL DEFAULT 0,

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
        tipo_precio TEXT,
        iva_porcentaje NUMERIC(5,2) NOT NULL DEFAULT 0,
        iva_valor REAL NOT NULL DEFAULT 0
    )
    """)

    cursor.execute("ALTER TABLE facturas ADD COLUMN IF NOT EXISTS subtotal REAL DEFAULT 0")
    cursor.execute("ALTER TABLE facturas ADD COLUMN IF NOT EXISTS iva_total REAL DEFAULT 0")
    cursor.execute("ALTER TABLE detalle_factura ADD COLUMN IF NOT EXISTS iva_porcentaje NUMERIC(5,2) NOT NULL DEFAULT 0")
    cursor.execute("ALTER TABLE detalle_factura ADD COLUMN IF NOT EXISTS iva_valor REAL NOT NULL DEFAULT 0")

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
    
    # Índices para las consultas que más se repiten en la aplicación.
    # IF NOT EXISTS permite ejecutar la inicialización varias veces sin cambiar datos.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS login_intentos (
        clave TEXT PRIMARY KEY,
        intentos INTEGER NOT NULL DEFAULT 0,
        primer_intento TIMESTAMPTZ NOT NULL DEFAULT now(),
        bloqueado_hasta TIMESTAMPTZ
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_productos_empresa_activo ON productos (empresa_id, activo, id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_productos_empresa_codigo ON productos (empresa_id, codigo_barras)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_productos_empresa_nombre ON productos (empresa_id, nombre)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_empresa_estado_elim ON pedidos (empresa_id, estado, eliminado, id DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_empresa_elim ON pedidos (empresa_id, eliminado, id DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_facturas_empresa_id ON facturas (empresa_id, id DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_facturas_empresa_fecha ON facturas (empresa_id, fecha)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_facturas_empresa_cliente ON facturas (empresa_id, cliente, id DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_empresa_cliente ON pedidos (empresa_id, cliente, id DESC)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_detalle_factura_factura ON detalle_factura (factura_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventario_empresa_codigo ON inventario (empresa_id, codigo_barras)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventario_empresa_producto ON inventario (empresa_id, producto)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_empresa_id ON usuarios (empresa_id, id DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventario_empresa_producto_codigo ON inventario (empresa_id, producto, codigo_barras)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pagos_credito_factura_empresa ON pagos_credito (factura_id, empresa_id, id DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recibos_abono_factura_empresa ON recibos_abono (factura_id, empresa_id, id DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clientes_empresa_nombre ON clientes (empresa_id, nombre)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_creditos_empresa_saldo ON creditos (empresa_id, saldo)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pagos_credito_factura ON pagos_credito (factura_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recibos_abono_factura ON recibos_abono (factura_id)")

    cursor.execute("SELECT COUNT(*) FROM empresas") 
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO empresas (nombre) VALUES ('Mi Empresa')")
        cursor.execute("INSERT INTO empresas (nombre) VALUES ('Empresa Demo')")
        print("🔥 DB inicializada")

    # Tablas del módulo de caja (nuevas; no alteran datos históricos).
    cursor.execute("""CREATE TABLE IF NOT EXISTS cajas (
        id SERIAL PRIMARY KEY, empresa_id INTEGER NOT NULL, estado TEXT NOT NULL DEFAULT 'abierta',
        base_inicial NUMERIC(14,2) NOT NULL DEFAULT 0, abierta_en TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Bogota'),
        abierta_por TEXT, cerrada_en TIMESTAMP, cerrada_por TEXT
    )""")
    cursor.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_caja_activa_empresa ON cajas(empresa_id) WHERE estado IN ('abierta','en_cuadre')""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS movimientos_caja (
        id SERIAL PRIMARY KEY, caja_id INTEGER NOT NULL REFERENCES cajas(id), empresa_id INTEGER NOT NULL,
        fecha TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Bogota'), tipo TEXT NOT NULL,
        metodo_pago TEXT NOT NULL DEFAULT 'efectivo', valor NUMERIC(14,2) NOT NULL,
        concepto TEXT NOT NULL DEFAULT '', factura_id INTEGER, usuario TEXT, origen TEXT NOT NULL DEFAULT 'manual'
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS cuadres_caja (
        id SERIAL PRIMARY KEY, caja_id INTEGER NOT NULL REFERENCES cajas(id), empresa_id INTEGER NOT NULL,
        fecha TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Bogota'), usuario TEXT,
        esperado_efectivo NUMERIC(14,2) NOT NULL DEFAULT 0, contado_efectivo NUMERIC(14,2) NOT NULL DEFAULT 0,
        esperado_tarjeta NUMERIC(14,2) NOT NULL DEFAULT 0, contado_tarjeta NUMERIC(14,2) NOT NULL DEFAULT 0,
        esperado_nequi NUMERIC(14,2) NOT NULL DEFAULT 0, contado_nequi NUMERIC(14,2) NOT NULL DEFAULT 0,
        observacion TEXT, estado TEXT NOT NULL DEFAULT 'vigente'
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS cierres_caja (
        id SERIAL PRIMARY KEY, caja_id INTEGER NOT NULL UNIQUE REFERENCES cajas(id), empresa_id INTEGER NOT NULL,
        fecha TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Bogota'), usuario TEXT,
        total_efectivo NUMERIC(14,2) NOT NULL DEFAULT 0, total_tarjeta NUMERIC(14,2) NOT NULL DEFAULT 0,
        total_nequi NUMERIC(14,2) NOT NULL DEFAULT 0, diferencia_efectivo NUMERIC(14,2) NOT NULL DEFAULT 0,
        diferencia_tarjeta NUMERIC(14,2) NOT NULL DEFAULT 0, diferencia_nequi NUMERIC(14,2) NOT NULL DEFAULT 0,
        observacion TEXT, movimientos_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb
    )""")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_caja_empresa_fecha ON movimientos_caja(empresa_id, fecha DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cuadres_caja_empresa_fecha ON cuadres_caja(empresa_id, fecha DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cierres_caja_empresa_fecha ON cierres_caja(empresa_id, fecha DESC)")

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
    
MAX_INTENTOS_LOGIN = 5
VENTANA_LOGIN_MIN = 15


def segundos_bloqueo_login(clave):
    """Segundos que faltan para poder volver a intentar (0 = sin bloqueo)."""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT CEIL(EXTRACT(EPOCH FROM (bloqueado_hasta - now())))
        FROM login_intentos
        WHERE clave = %s AND bloqueado_hasta > now()
    """, (clave,))
    fila = cursor.fetchone()
    conn.close()
    return int(fila[0]) if fila and fila[0] else 0


def registrar_fallo_login(clave):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO login_intentos (clave, intentos, primer_intento)
        VALUES (%s, 0, now())
        ON CONFLICT (clave) DO NOTHING
    """, (clave,))
    cursor.execute("""
        SELECT intentos,
               primer_intento < now() - make_interval(mins => %s) AS vencido
        FROM login_intentos
        WHERE clave = %s
        FOR UPDATE
    """, (VENTANA_LOGIN_MIN, clave))
    fila = cursor.fetchone()
    intentos = 1 if fila["vencido"] else fila["intentos"] + 1
    if intentos >= MAX_INTENTOS_LOGIN:
        cursor.execute("""
            UPDATE login_intentos
            SET intentos = %s,
                primer_intento = CASE WHEN %s THEN now() ELSE primer_intento END,
                bloqueado_hasta = now() + make_interval(mins => %s)
            WHERE clave = %s
        """, (intentos, fila["vencido"], VENTANA_LOGIN_MIN, clave))
    else:
        cursor.execute("""
            UPDATE login_intentos
            SET intentos = %s,
                primer_intento = CASE WHEN %s THEN now() ELSE primer_intento END,
                bloqueado_hasta = NULL
            WHERE clave = %s
        """, (intentos, fila["vencido"], clave))
    conn.commit()
    conn.close()


def limpiar_intentos_login(clave):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM login_intentos WHERE clave = %s", (clave,))
    conn.commit()
    conn.close()


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
    try:
        clave_ok = bcrypt.checkpw(
            password.encode("utf-8"),
            resultado["password"].encode("utf-8")
        )
    except ValueError:
        clave_ok = False

    if not clave_ok:
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

def obtener_clientes(empresa_id, conn=None):

    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM clientes
        WHERE empresa_id = %s
        ORDER BY nombre ASC
    """, (empresa_id,))

    data = cursor.fetchall()

    if _own_conn:
        conn.close()

    return data

def obtener_empresas(conn=None):
    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre FROM empresas")
    data = cursor.fetchall()

    if _own_conn:
        conn.close()
    return data

def obtener_productos(empresa_id, conn=None):
    

    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nombre, precio_mayorista, precio_individual,
               precio_mostrador, costo, codigo_barras, empresa_id, activo, iva_porcentaje
        FROM productos
        WHERE empresa_id = %s
          AND activo = TRUE
        ORDER BY id DESC
    """, (empresa_id,))

    productos = cursor.fetchall()
    if _own_conn:
        conn.close()
    return productos

def obtener_precio_producto(nombre, empresa_id, tipo_precio, conn=None):
    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT precio_mayorista,
               precio_individual,
               precio_mostrador
        FROM productos
        WHERE nombre = %s
          AND empresa_id = %s
          AND activo = 1
        LIMIT 1
    """, (nombre, empresa_id))

    resultado = cursor.fetchone()

    if _own_conn:
        conn.close()

    if not resultado:
        return 0

    if tipo_precio == "mayorista":
        return resultado["precio_mayorista"] or 0

    if tipo_precio == "individual":
        return resultado["precio_individual"] or 0

    return resultado["precio_mostrador"] or 0

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

def obtener_pedidos(empresa_id, conn=None):
    _own_conn = conn is None
    if _own_conn:
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
    if _own_conn:
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
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

def obtener_pedidos_pendientes(empresa_id, conn=None):
    _own_conn = conn is None
    if _own_conn:
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
    if _own_conn:
        conn.close()
    return data


def obtener_pedidos_entregados(empresa_id, conn=None):
    _own_conn = conn is None
    if _own_conn:
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
    if _own_conn:
        conn.close()
    return data


def obtener_pedidos_eliminados(empresa_id, conn=None):
    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM pedidos
        WHERE empresa_id = %s
        AND eliminado = 1
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()
    if _own_conn:
        conn.close()
    return data

def cambiar_estado(id, estado, empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    from datetime import datetime
    if estado == "entregado":
        fecha_entrega = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        fecha_entrega = None

    cursor.execute("""
        UPDATE pedidos
        SET estado=%s, fecha_entrega=%s
        WHERE id=%s AND empresa_id=%s
    """, (estado, fecha_entrega, id, empresa_id))

    conn.commit()
    conn.close()


def eliminar_pedido(id, empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE pedidos
        SET eliminado=1
        WHERE id=%s AND empresa_id=%s
    """, (id, empresa_id))

    conn.commit()
    conn.close()

def recuperar_pedido(id, empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE pedidos
        SET eliminado=0
        WHERE id=%s AND empresa_id=%s
    """, (id, empresa_id))

    conn.commit()
    conn.close()

from db import ahora

def total_ventas_dia(empresa_id, conn=None):
    """Total facturado hoy para la empresa actual."""
    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(total), 0) AS total
        FROM facturas
        WHERE fecha >= CURRENT_DATE
          AND fecha < (CURRENT_DATE + INTERVAL '1 day')
          AND empresa_id = %s
    """, (empresa_id,))

    total = cursor.fetchone()["total"] or 0
    if _own_conn:
        conn.close()
    return total


def total_ventas_mes(empresa_id, conn=None):
    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(total), 0) AS total
        FROM facturas
        WHERE fecha >= DATE_TRUNC('month', CURRENT_DATE)
          AND fecha < (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month')
          AND empresa_id = %s
    """, (empresa_id,))

    total = cursor.fetchone()["total"] or 0
    if _own_conn:
        conn.close()
    return total


def facturas_emitidas_hoy(empresa_id, conn=None):
    """Cantidad de facturas emitidas hoy para la empresa actual."""
    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM facturas
        WHERE fecha >= CURRENT_DATE
          AND fecha < (CURRENT_DATE + INTERVAL '1 day')
          AND empresa_id = %s
    """, (empresa_id,))

    total = cursor.fetchone()["total"] or 0
    if _own_conn:
        conn.close()
    return total


def saldo_cartera(empresa_id, conn=None):
    """Saldo pendiente de cartera de la empresa actual."""
    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(saldo), 0) AS total
        FROM creditos
        WHERE empresa_id = %s
          AND COALESCE(saldo, 0) > 0
    """, (empresa_id,))

    total = cursor.fetchone()["total"] or 0
    if _own_conn:
        conn.close()
    return total


def obtener_metricas_dashboard(empresa_id, conn=None):
    """Obtiene las métricas principales del dashboard en una sola ida a PostgreSQL."""
    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COALESCE(SUM(CASE
                WHEN fecha >= CURRENT_DATE
                 AND fecha < (CURRENT_DATE + INTERVAL '1 day')
                THEN total ELSE 0 END), 0) AS total_dia,
            COALESCE(SUM(CASE
                WHEN fecha >= DATE_TRUNC('month', CURRENT_DATE)
                 AND fecha < (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month')
                THEN total ELSE 0 END), 0) AS total_mes,
            COUNT(*) FILTER (
                WHERE fecha >= CURRENT_DATE
                  AND fecha < (CURRENT_DATE + INTERVAL '1 day')
            ) AS facturas_hoy,
            COALESCE((
                SELECT SUM(c.saldo)
                FROM creditos c
                WHERE c.empresa_id = %s
                  AND COALESCE(c.saldo, 0) > 0
            ), 0) AS cartera_pendiente
        FROM facturas
        WHERE empresa_id = %s
    """, (empresa_id, empresa_id))

    data = cursor.fetchone()
    if _own_conn:
        conn.close()
    return data

def productos_top_5_mes(empresa_id, conn=None):
    """Devuelve los 5 productos con más unidades vendidas en el mes actual."""
    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            d.producto,
            COALESCE(SUM(d.cantidad), 0) AS total
        FROM detalle_factura d
        INNER JOIN facturas f ON f.id = d.factura_id
        WHERE f.empresa_id = %s
          AND f.fecha >= DATE_TRUNC('month', CURRENT_DATE)
          AND f.fecha < (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month')
        GROUP BY d.producto
        ORDER BY total DESC, d.producto ASC
        LIMIT 5
    """, (empresa_id,))

    data = cursor.fetchall()
    if _own_conn:
        conn.close()
    return data


def producto_top_mes(empresa_id, data=None, conn=None):
    """Compatibilidad: devuelve únicamente el producto número 1."""
    if data is None:
        data = productos_top_5_mes(empresa_id, conn=conn)
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
    domiciliario="",
    metodo_pago=None,
    usuario=None
):

    import os
    from datetime import datetime
    from db import ahora
    conn = conectar()
    cursor = conn.cursor()

    # Bloquear nuevas ventas durante el cuadre y asegurar caja activa por empresa.
    cursor.execute("SELECT id, estado FROM cajas WHERE empresa_id=%s AND estado IN ('abierta','en_cuadre') FOR UPDATE", (empresa_id,))
    caja_activa = cursor.fetchone()
    if caja_activa and caja_activa["estado"] != "abierta":
        conn.close()
        raise ValueError("La caja está en cuadre. No se pueden registrar ventas hasta cancelar el cuadre o abrir una nueva caja.")
    if not caja_activa:
        cursor.execute("INSERT INTO cajas(empresa_id, estado, base_inicial, abierta_por) VALUES (%s,'abierta',0,%s) RETURNING id", (empresa_id, usuario))
        caja_id = cursor.fetchone()[0]
    else:
        caja_id = caja_activa["id"]

    fecha = ahora()

    subtotal_factura = 0
    iva_factura = 0

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
        iva_porcentaje = float(p.get("iva_porcentaje") or 0)

        # Los precios configurados en Productos son base antes de IVA.
        linea_subtotal = precio * cantidad
        linea_iva = int((linea_subtotal * iva_porcentaje / 100) + 0.5)
        subtotal_factura += linea_subtotal
        iva_factura += linea_iva

    total = subtotal_factura + iva_factura
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

    # Método de pago: en contado es el pago completo; en crédito es el del
    # abono inicial (si no hubo abono, queda vacío).
    if metodo_pago not in METODOS_PAGO or abono <= 0:
        metodo_pago = None

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
            metodo_pago,
            subtotal,
            iva_total,
            empresa_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        metodo_pago,
        subtotal_factura,
        iva_factura,
        empresa_id
    ))

    factura_id = cursor.fetchone()[0]

    # Registrar únicamente dinero realmente recibido (no el saldo a crédito).
    if abono > 0 and metodo_pago:
        cursor.execute("""INSERT INTO movimientos_caja
            (caja_id, empresa_id, fecha, tipo, metodo_pago, valor, concepto, factura_id, usuario, origen)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'factura')""",
            (caja_id, empresa_id, fecha, 'venta_contado' if tipo_venta != 'credito' else 'abono_inicial', metodo_pago, abono, 'Pago recibido de factura', factura_id, usuario))

    # =========================
    # DETALLE FACTURA
    # =========================
    for p in productos:

        precio = float(p.get("precio") or 0)
        cantidad = int(p.get("cantidad") or 0)
        iva_porcentaje = float(p.get("iva_porcentaje") or 0)
        # Se guarda el impuesto aplicado por línea para que las facturas históricas no cambien.
        subtotal = precio * cantidad
        iva_valor = int((subtotal * iva_porcentaje / 100) + 0.5)

        cursor.execute("""
            INSERT INTO detalle_factura (
                factura_id, producto, cantidad, precio_unitario, subtotal,
                iva_porcentaje, iva_valor
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            factura_id, p.get("producto"), cantidad, precio, subtotal,
            iva_porcentaje, iva_valor
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

def obtener_inventario(empresa_id, conn=None):
    _own_conn = conn is None
    if _own_conn:
        conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.producto, i.stock_unidades, i.codigo_barras,
               p.id AS producto_id, p.foto_mimetype,
               CASE WHEN p.foto IS NOT NULL THEN TRUE ELSE FALSE END AS tiene_foto
        FROM inventario i
        LEFT JOIN productos p
          ON p.codigo_barras = i.codigo_barras
         AND p.empresa_id = i.empresa_id
        WHERE i.empresa_id = %s
        ORDER BY i.producto ASC
    """, (empresa_id,))
    data = cursor.fetchall()
    if _own_conn:
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

        precio_unitario = obtener_precio_producto(p["producto"], empresa_id, "mostrador", conn=conn)

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
        tipo_precio,
        conn=conn
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


def registrar_abono(factura_id, abono, observacion, empresa_id, metodo_pago=None, usuario=None):
    """Registra un abono. Lanza ValueError con un mensaje legible si no es válido."""
    import math
    from datetime import datetime

    try:
        abono = round(float(abono), 2)
    except (TypeError, ValueError):
        raise ValueError("El valor del abono no es un número válido.")
    if not math.isfinite(abono) or abono <= 0:
        raise ValueError("El abono debe ser mayor que cero.")

    metodo_pago = (metodo_pago or "").strip().lower()
    if metodo_pago not in METODOS_PAGO:
        raise ValueError("Selecciona un método de pago válido (efectivo, tarjeta o nequi).")

    conn = conectar()
    try:
        cursor = conn.cursor()

        # Bloquea la fila: dos abonos simultáneos no se pisan.
        cursor.execute("""
            SELECT *
            FROM facturas
            WHERE id=%s
            AND empresa_id=%s
            FOR UPDATE
        """, (factura_id, empresa_id))

        factura = cursor.fetchone()

        if not factura:
            raise ValueError("Factura no encontrada.")

        cursor.execute("SELECT id, estado FROM cajas WHERE empresa_id=%s AND estado IN ('abierta','en_cuadre') FOR UPDATE", (empresa_id,))
        caja_activa = cursor.fetchone()
        if caja_activa and caja_activa["estado"] != "abierta":
            raise ValueError("La caja está en cuadre. No se pueden registrar abonos hasta cancelar el cuadre o abrir una nueva caja.")
        if not caja_activa:
            cursor.execute("INSERT INTO cajas(empresa_id, estado, base_inicial) VALUES (%s,'abierta',0) RETURNING id", (empresa_id,))
            caja_id = cursor.fetchone()[0]
        else:
            caja_id = caja_activa['id']

        total = float(factura["total"] or 0)
        abono_actual = float(factura["abono"] or 0)
        saldo_anterior = round(total - abono_actual, 2)

        if saldo_anterior <= 0:
            raise ValueError("Esta factura ya está pagada.")
        if abono > saldo_anterior + 0.005:
            raise ValueError(
                f"El abono no puede superar el saldo pendiente (${saldo_anterior:,.0f})."
            )

        nuevo_abono = round(abono_actual + abono, 2)
        saldo = round(total - nuevo_abono, 2)

        if saldo <= 0:
            estado = "pagado"
            saldo = 0
        else:
            estado = "parcial"

        cursor.execute("""
            UPDATE facturas
            SET abono=%s,
                estado=%s
            WHERE id=%s
            AND empresa_id=%s
        """, (nuevo_abono, estado, factura_id, empresa_id))

        cursor.execute("""
            UPDATE creditos
            SET abonado=%s,
                saldo=%s,
                estado=%s
            WHERE factura_id=%s
            AND empresa_id=%s
        """, (nuevo_abono, saldo, estado, factura_id, empresa_id))

        fecha = ahora()
        cursor.execute("""INSERT INTO movimientos_caja
            (caja_id, empresa_id, fecha, tipo, metodo_pago, valor, concepto, factura_id, usuario, origen)
            VALUES (%s,%s,%s,'abono_cartera',%s,%s,%s,%s,%s,'abono')""",
            (caja_id, empresa_id, fecha, metodo_pago, abono, observacion or 'Abono de cartera', factura_id, usuario))

        cursor.execute("""
            INSERT INTO pagos_credito (
                factura_id, cliente, abono, fecha, observacion, metodo_pago, empresa_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (factura_id, factura["cliente"], abono, fecha, observacion, metodo_pago, empresa_id))

        cursor.execute("""
            INSERT INTO recibos_abono (
                factura_id, cliente, valor_abono, saldo_anterior,
                saldo_nuevo, fecha, metodo_pago, empresa_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            factura_id, factura["cliente"], abono, saldo_anterior,
            saldo, fecha, metodo_pago, empresa_id
        ))

        recibo_id = cursor.fetchone()[0]
        conn.commit()
        return recibo_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

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
