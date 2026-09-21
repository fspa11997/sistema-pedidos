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
