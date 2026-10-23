# ST Gestión — PostgreSQL + Railway

Aplicación web de gestión de pedidos, facturación e inventario con Flask y PostgreSQL.

## Tecnologías

- Python
- Flask
- PostgreSQL
- psycopg2
- Bcrypt
- Gunicorn
- Python Barcode

## Base de datos

El proyecto ya no usa SQLite. La aplicación obtiene la conexión desde la variable de entorno:

`DATABASE_URL`

En Railway, al agregar un servicio PostgreSQL y conectarlo con el servicio web, Railway proporciona esta variable automáticamente.

## Variables de entorno

| Variable | Obligatoria | Uso |
|---|---|---|
| `DATABASE_URL` | Sí | Conexión a PostgreSQL (Railway la da sola). |
| `SECRET_KEY` | Sí | Firma las sesiones. Genera una con `python -c "import secrets; print(secrets.token_hex(32))"`. La app no arranca sin ella. |
| `SUPERADMIN_PASSWORD` | Recomendada | Clave inicial del usuario `superadmin`. Si no se define, se genera una aleatoria y se imprime una vez en los logs. Cámbiala después de entrar. |

## Reglas de seguridad

- Contraseñas nuevas: mínimo 8 caracteres, combinando letras y números (máximo 72 bytes).
- Inicio de sesión: tras 5 intentos fallidos desde la misma IP para un usuario, se bloquea 15 minutos.
- Abonos: deben ser mayores que cero y no pueden superar el saldo pendiente de la factura.
- Métodos de pago: efectivo, tarjeta o nequi. Obligatorio en ventas de contado, en crédito con abono inicial y en cada abono de cartera.
- Roles permitidos al crear usuarios: `admin` y `vendedor`.

## Ejecutar localmente

1. Instalar dependencias:

```powershell
py -m pip install -r requirements.txt
```

2. Crear una base de datos PostgreSQL local y configurar `DATABASE_URL`.

Ejemplo en PowerShell:

```powershell
$env:DATABASE_URL="postgresql://USUARIO:CONTRASEÑA@localhost:5432/st_gestion"
```

3. Inicializar la base de datos:

```powershell
py 1-init_db.py
```

4. Ejecutar:

```powershell
py app.py
```

## Desplegar en Railway

1. Sube el proyecto a GitHub.
2. Crea un proyecto en Railway.
3. Agrega un servicio PostgreSQL.
4. Agrega el servicio web desde el repositorio de GitHub.
5. Railway debe proporcionar `DATABASE_URL` al servicio web.
6. El comando de inicio está definido en `Procfile`:

```text
web: gunicorn app:app
```

La aplicación crea las tablas de PostgreSQL automáticamente al iniciar.

## Importante

El archivo `pedidos.db` de la versión SQLite no se utiliza en esta versión. Los datos existentes de SQLite no se migran automáticamente; si necesitas conservarlos, hay que hacer una migración de datos hacia PostgreSQL antes de poner el sistema en producción.
