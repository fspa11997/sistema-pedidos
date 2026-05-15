import sqlite3
import bcrypt
from datetime import datetime

DB = "pedidos.db"

def conectar():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_db():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS empresas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE,
        password TEXT,
        rol TEXT NOT NULL DEFAULT 'vendedor',
        empresa_id INTEGER
    )
    """)
    

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        precio_mayorista REAL,
        precio_individual REAL,
        precio_mostrador REAL,
        costo REAL,
        empresa_id INTEGER,
        activo INTEGER DEFAULT 1
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT,
        producto TEXT,
        direccion TEXT,
        ciudad TEXT,
        telefono TEXT,
        domiciliario TEXT,
        cantidad INTEGER,
        peso REAL,

        precio REAL DEFAULT 0,
        abono REAL DEFAULT 0,

        tipo_precio TEXT,

        estado TEXT DEFAULT 'pendiente',
        eliminado INTEGER DEFAULT 0,

        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_entrega TIMESTAMP,

        empresa_id INTEGER
    );
    """)
    
        # =========================
    # FACTURAS
    # =========================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facturas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        factura_id INTEGER,
        producto TEXT,
        cantidad INTEGER,
        peso REAL,
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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto TEXT,
        stock_unidades INTEGER DEFAULT 0,
        stock_kilos REAL DEFAULT 0,
        empresa_id INTEGER
    )
    """)

    # =========================
    # MOVIMIENTOS INVENTARIO
    # =========================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movimientos_inventario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto TEXT,
        tipo TEXT,
        cantidad INTEGER,
        peso REAL,
        fecha TEXT,
        empresa_id INTEGER
    )
    """)

    # =========================
    # MENSAJEROS
    # =========================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mensajeros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        telefono TEXT,
        empresa_id INTEGER
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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



def crear_usuario(usuario, password, rol, empresa_id):
    import bcrypt

    conn = conectar()
    cursor = conn.cursor()

    # verificar si existe
    cursor.execute("""
        SELECT id FROM usuarios WHERE usuario = ? AND empresa_id = ?
    """, (usuario, empresa_id))

    if cursor.fetchone():
        return False  # ya existe

    # hash password
    hash_password = bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    )

    cursor.execute("""
        INSERT INTO usuarios (usuario, password, rol, empresa_id)
        VALUES (?, ?, ?, ?)
    """, (usuario, hash_password, rol, empresa_id))

    conn.commit()
    conn.close()

    return True
    
def validar_usuario(usuario, password, empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, usuario, password, rol, empresa_id
        FROM usuarios
        WHERE usuario=? AND empresa_id=?
    """, (usuario, empresa_id))

    user = cursor.fetchone()
    conn.close()

    if not user:
        return None

    password_bd = user["password"]

    if isinstance(password_bd, str):
        password_bd = password_bd.encode('utf-8')

    if bcrypt.checkpw(password.encode('utf-8'), password_bd):
        return user

    return None

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
        VALUES (?, ?, ?, ?, ?, ?, ?)
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
        WHERE empresa_id = ?
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
    

    conn = sqlite3.connect("pedidos.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM productos
        WHERE empresa_id = ?
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
        WHERE nombre=? AND empresa_id=?
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
        WHERE nombre = ? AND empresa_id = ?
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
            peso,  -- 🔥 AQUÍ
            precio,
            fecha,
            fecha_entrega,
            estado,
            eliminado
        FROM pedidos
        WHERE empresa_id = ?
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        WHERE empresa_id = ?
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
        WHERE empresa_id = ?
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
        WHERE empresa_id = ?
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

    if estado == "entregado":
        fecha_entrega = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        fecha_entrega = None

    cursor.execute("""
        UPDATE pedidos
        SET estado=?, fecha_entrega=?
        WHERE id=?
    """, (estado, fecha_entrega, id))

    conn.commit()
    conn.close()


def eliminar_pedido(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE pedidos
        SET eliminado=1
        WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

def recuperar_pedido(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE pedidos
        SET eliminado=0
        WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

def total_ventas_dia(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT SUM(precio) as total
        FROM pedidos
        WHERE DATE(fecha) = DATE('now')
        AND empresa_id = ?
        AND eliminado = 0
    """, (empresa_id,))

    total = cursor.fetchone()["total"]
    conn.close()

    return total or 0

def total_ventas_mes(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT SUM(precio) as total
        FROM pedidos
        WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m', 'now')
        AND empresa_id = ?
        AND eliminado = 0
    """, (empresa_id,))

    total = cursor.fetchone()["total"]
    conn.close()

    return total or 0
def producto_top_mes(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT producto, SUM(cantidad) as total
        FROM pedidos
        WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m', 'now')
        AND empresa_id = ?
        AND eliminado = 0
        GROUP BY producto
        ORDER BY total DESC
        LIMIT 1
    """, (empresa_id,))

    data = cursor.fetchone()
    conn.close()

    return data

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

    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect("pedidos.db")
    conn.row_factory = sqlite3.Row
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
        peso = float(p.get("peso") or 0)

        subtotal = precio * peso
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    factura_id = cursor.lastrowid

    # =========================
    # DETALLE FACTURA
    # =========================
    for p in productos:

        precio = float(p.get("precio") or 0)
        peso = float(p.get("peso") or 0)
        cantidad = int(p.get("cantidad") or 0)

        subtotal = precio * peso

        cursor.execute("""
            INSERT INTO detalle_factura (
                factura_id,
                producto,
                cantidad,
                peso,
                precio_unitario,
                subtotal
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            factura_id,
            p.get("producto"),
            cantidad,
            peso,
            precio,
            subtotal
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    import sqlite3

    conn = sqlite3.connect("pedidos.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM facturas
        WHERE id = ? AND empresa_id = ?
    """, (factura_id, empresa_id))

    factura = cursor.fetchone()

    conn.close()
    return factura

def obtener_detalles_factura(factura_id):
    import sqlite3

    conn = sqlite3.connect("pedidos.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM detalle_factura
        WHERE factura_id = ?
    """, (factura_id,))

    detalles = cursor.fetchall()

    conn.close()
    return detalles

def registrar_compra(producto, cantidad, peso, empresa_id):
    from datetime import datetime

    conn = conectar()
    cursor = conn.cursor()

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 🔍 verificar si existe
    cursor.execute("""
        SELECT id FROM inventario
        WHERE producto = ? AND empresa_id = ?
    """, (producto, empresa_id))

    existe = cursor.fetchone()

    if existe:
        cursor.execute("""
            UPDATE inventario
            SET stock_unidades = stock_unidades + ?,
                stock_kilos = stock_kilos + ?
            WHERE producto = ? AND empresa_id = ?
        """, (cantidad, peso, producto, empresa_id))
    else:
        cursor.execute("""
            INSERT INTO inventario (producto, stock_unidades, stock_kilos, empresa_id)
            VALUES (?, ?, ?, ?)
        """, (producto, cantidad, peso, empresa_id))

    conn.commit()
    conn.close()

def obtener_inventario(empresa_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT producto, stock_unidades, stock_kilos
        FROM inventario
        WHERE empresa_id = ?
    """, (empresa_id,))

    data = cursor.fetchall()
    conn.close()
    return data

def obtener_facturas(empresa_id):
    import sqlite3

    conn = sqlite3.connect("pedidos.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM facturas
        WHERE empresa_id = ?
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()

    conn.close()
    return data

def crear_factura_empresa(empresa_id):
    from datetime import datetime
    import sqlite3

    conn = sqlite3.connect("pedidos.db")
    cursor = conn.cursor()

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 🔥 obtener pedidos pendientes
    cursor.execute("""
        SELECT * FROM pedidos
        WHERE empresa_id = ? AND estado = 'pendiente' AND eliminado = 0
    """, (empresa_id,))

    pedidos = cursor.fetchall()

    if not pedidos:
        conn.close()
        return None

    total = 0

    # 🔥 crear factura
    cursor.execute("""
        INSERT INTO facturas (cliente, fecha, total, empresa_id)
        VALUES (?, ?, 0, ?)
    """, ("FACTURA EMPRESA", fecha, empresa_id))

    factura_id = cursor.lastrowid

    for p in pedidos:

        precio_unitario = obtener_precio_producto(p["producto"], empresa_id)

        subtotal = precio_unitario * p["peso"]

        total += subtotal

        cursor.execute("""
            INSERT INTO detalle_factura (factura_id, producto, cantidad, peso, precio_unitario, subtotal)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            factura_id,
            p["producto"],
            p["cantidad"],
            p["peso"],
            precio_unitario,
            subtotal
        ))

        # 🔥 marcar como entregado o facturado
        cursor.execute("""
            UPDATE pedidos
            SET estado = 'entregado'
            WHERE id = ?
        """, (p["id"],))

    cursor.execute("UPDATE facturas SET total=? WHERE id=?", (total, factura_id))

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
    peso,
    empresa_id,
    tipo_precio
):

    import sqlite3

    conn = sqlite3.connect("pedidos.db")
    cursor = conn.cursor()

    # 🔥 obtener precio correcto
    precio_unitario = obtener_precio_producto(
        producto,
        empresa_id,
        tipo_precio
    )

    # 🔥 calcular total correcto
    total = precio_unitario * (peso if peso > 0 else cantidad)

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
            peso,
            precio,
            empresa_id,
            estado,
            eliminado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', 0)
    """, (
        factura_id,
        cliente,
        producto,
        direccion,
        ciudad,
        telefono,
        domiciliario,
        cantidad,
        peso,
        total,
        empresa_id
    ))

    conn.commit()
    conn.close()

def descontar_inventario(producto, cantidad, peso, empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    # 🔥 restar unidades
    cursor.execute("""
        UPDATE inventario
        SET stock_unidades = stock_unidades - ?
        WHERE producto = ? AND empresa_id = ?
    """, (cantidad, producto, empresa_id))

    # 🔥 restar kilos
    cursor.execute("""
        UPDATE inventario
        SET stock_kilos = stock_kilos - ?
        WHERE producto = ? AND empresa_id = ?
    """, (peso, producto, empresa_id))

    conn.commit()
    conn.close()

def crear_credito(cliente, factura_id, total, empresa_id):

    conn = conectar()
    cursor = conn.cursor()

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO creditos (
            cliente,
            factura_id,
            total,
            saldo,
            fecha,
            empresa_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
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
        SELECT saldo, abonado FROM creditos WHERE id=?
    """, (credito_id,))

    c = cursor.fetchone()

    nuevo_abono = c["abonado"] + valor
    nuevo_saldo = c["saldo"] - valor

    estado = "pagado" if nuevo_saldo <= 0 else "pendiente"

    cursor.execute("""
        UPDATE creditos
        SET abonado=?, saldo=?, estado=?
        WHERE id=?
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
        WHERE empresa_id=?
        ORDER BY id DESC
    """, (empresa_id,))

    data = cursor.fetchall()

    conn.close()
    return data

def registrar_abono(factura_id, abono, observacion, empresa_id):

    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect("pedidos.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # =========================
    # FACTURA
    # =========================
    cursor.execute("""
        SELECT *
        FROM facturas
        WHERE id=?
        AND empresa_id=?
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
        SET abono=?,
            estado=?
        WHERE id=?
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
        SET abonado=?,
            saldo=?,
            estado=?
        WHERE factura_id=?
    """, (
        nuevo_abono,
        saldo,
        estado,
        factura_id
    ))

    # =========================
    # HISTORIAL
    # =========================
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO pagos_credito (
            factura_id,
            cliente,
            abono,
            fecha,
            observacion,
            empresa_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
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
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        factura_id,
        factura["cliente"],
        abono,
        saldo_anterior,
        saldo,
        fecha,
        empresa_id
    ))

    recibo_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return recibo_id

def obtener_historial_abonos(factura_id, empresa_id):

    import sqlite3

    conn = sqlite3.connect("pedidos.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM pagos_credito
        WHERE factura_id=?
        AND empresa_id=?
        ORDER BY id DESC
    """, (
        factura_id,
        empresa_id
    ))

    pagos = cursor.fetchall()

    conn.close()

    return pagos