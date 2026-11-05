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
| `LEGAL_TITULAR` | Antes de vender | Nombre o razón social que aparece en los Términos y la Política de privacidad. |
| `LEGAL_DOCUMENTO` | Antes de vender | NIT o cédula del titular. |
| `LEGAL_EMAIL` | Antes de vender | Correo para soporte y para ejercer derechos de datos personales. |
| `LEGAL_CIUDAD` | Antes de vender | Ciudad de domicilio. |

## Reglas de seguridad

- Contraseñas nuevas: mínimo 8 caracteres, combinando letras y números (máximo 72 bytes).
- Inicio de sesión: tras 5 intentos fallidos desde la misma IP para un usuario, se bloquea 15 minutos.
- Abonos: deben ser mayores que cero y no pueden superar el saldo pendiente de la factura.
- Métodos de pago: efectivo, tarjeta o nequi. Obligatorio en ventas de contado, en crédito con abono inicial y en cada abono de cartera.
- Roles permitidos al crear usuarios: `admin` y `vendedor`.

## Suscripciones por empresa

Cada empresa tiene `plan` (`prueba`, `basico`, `profesional`), `fecha_vencimiento` y un interruptor de acceso. Se administra desde el panel de empresas del `superadmin`.

- Una empresa nueva nace con plan `prueba` de 14 días.
- `fecha_vencimiento` es el **último día con acceso**. Vacía = sin vencimiento (así quedan las empresas que ya existían al migrar: nadie se bloquea por sorpresa).
- Si la empresa está suspendida o vencida, sus usuarios no pueden iniciar sesión y las sesiones abiertas se cierran. El `superadmin` global nunca se bloquea.
- Cinco días antes del vencimiento los usuarios ven un aviso en el dashboard.
- **Registrar pago** suma 30, 90 o 365 días: si aún no vence, suma desde la fecha actual de vencimiento; si ya venció, desde hoy.
- Los cambios se aplican de inmediato en el proceso que los hizo y en un máximo de 30 segundos en el otro worker de gunicorn.

## Monitoreo y respaldos

- `GET /health` devuelve `{"status":"ok"}` (503 si la base no responde). Configúralo en Railway como Healthcheck Path.
- Respaldos: ver [RESPALDOS.md](RESPALDOS.md) y `backup_db.py`.

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

## Gestion.exe: solo para uso interno

`Gestion.exe` se conecta **directamente** a la base de datos con las credenciales de `config.env`. Quien tenga ese archivo tiene acceso completo a los datos de **todas** las empresas. No lo entregues a clientes: ellos deben usar la aplicación web (que sí aísla los datos por empresa).
