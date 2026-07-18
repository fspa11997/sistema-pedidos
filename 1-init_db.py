from db import conectar, inicializar_db
import bcrypt
import os

# =========================
# DB (POSTGRES)
# =========================
conn = conectar()
cursor = conn.cursor()

# IMPORTANTE: crear tablas en Postgres
inicializar_db()

# =========================
# SUPERADMIN
# =========================
cursor.execute("""
    SELECT 1 FROM usuarios WHERE usuario=%s
""", ("superadmin",))

if not cursor.fetchone():

    password = "1234"
    hash_password = bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode("utf-8")

    cursor.execute("""
        INSERT INTO usuarios (usuario, password, rol, empresa_id)
        VALUES (%s, %s, %s, %s)
    """, ("superadmin", hash_password, "owner_global", 1))

# =========================
# PRODUCTOS
# =========================
productos = [
    ("Pechuga", 4000, 4500, 5000, 2500, 1),
    ("Muslo", 2000, 2500, 3000, 1200, 1)
]

for p in productos:

    cursor.execute("""
        SELECT 1 FROM productos WHERE nombre=%s AND empresa_id=%s
    """, (p[0], p[5]))

    if not cursor.fetchone():

        cursor.execute("""
            INSERT INTO productos (
                nombre, precio_mayorista, precio_individual,
                precio_mostrador, costo, empresa_id
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, p)

# =========================
# CLIENTES
# =========================
clientes = [
    ("steven", "cra 33b 32a49", "Cali", "0000000000", "cc", "1143870173", 1),
    ("St sas", "Zona industrial", "Bogotá", "3251628", "nit", "900123456", 1)
]

for c in clientes:

    cursor.execute("""
        SELECT 1 FROM clientes
        WHERE identificacion=%s AND empresa_id=%s
    """, (c[5], c[6]))

    if not cursor.fetchone():

        cursor.execute("""
            INSERT INTO clientes (
                nombre, direccion, ciudad,
                telefono, tipo_id, identificacion, empresa_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, c)

# =========================
# INVENTARIO
# =========================
inventario = [
    ("Pechuga", 100, 50.0, 1),
    ("Muslo", 200, 80.0, 1)
]

for i in inventario:

    cursor.execute("""
        SELECT 1 FROM inventario
        WHERE producto=%s AND empresa_id=%s
    """, (i[0], i[3]))

    if not cursor.fetchone():

        cursor.execute("""
            INSERT INTO inventario (
                producto, stock_unidades, stock_kilos, empresa_id
            )
            VALUES (%s, %s, %s, %s)
        """, i)

conn.commit()
conn.close()

print("✅ Sistema inicializado correctamente en PostgreSQL")