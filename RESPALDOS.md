# Respaldos de la base de datos

Perder la base de un cliente que paga es perder el cliente. Usa **las dos capas**:

## 1. Respaldos de Railway (lo primero)

En Railway abre el servicio **Postgres → pestaña Backups** y revisa si tu plan permite
programar respaldos automáticos (diarios). Si están disponibles, actívalos. Esta
disponibilidad depende del plan: confírmala en la pantalla, no la des por hecha.

## 2. Respaldo propio con `backup_db.py` (copia fuera de Railway)

Una copia en tu PC o en un disco externo te protege aunque falle Railway o se borre el servicio.

Requisitos: instalar las herramientas cliente de PostgreSQL (`pg_dump`, `pg_restore`) y
tenerlas en el PATH. Usa una versión igual o mayor a la del servidor.

```powershell
# URL PÚBLICA: Railway > servicio Postgres > Variables > DATABASE_PUBLIC_URL
$env:DATABASE_URL="postgresql://usuario:clave@host:puerto/railway"
py backup_db.py --verificar
```

- Crea `respaldos/AAAA-MM-DD_HHMM.dump` y conserva los últimos 14 (`--conservar N`).
- `--verificar` comprueba que el archivo se puede leer. Un respaldo que nunca se probó no es un respaldo.
- La carpeta `respaldos/` contiene datos de clientes: está en `.gitignore`, **no la subas a GitHub**.

### Automatizar en Windows (Programador de tareas)

```powershell
schtasks /Create /SC DAILY /ST 22:00 /TN "Respaldo ST Gestion" /TR "cmd /c cd /d C:\ruta\al\proyecto && py backup_db.py --verificar"
```

(Define `DATABASE_URL` en un `config.env` junto al script, o como variable de entorno del usuario.)

## Restaurar

Siempre prueba primero en una base vacía **distinta** de producción:

```powershell
pg_restore --no-owner --no-acl --clean --if-exists -d "postgresql://usuario:clave@host:puerto/base_de_prueba" respaldos\2026-11-05_2200.dump
```

Haz una prueba de restauración al menos una vez al mes.

## Monitoreo

La app responde `GET /health` (`{"status":"ok"}` o 503 si la base no responde).
En Railway: servicio web → **Settings → Deploy → Healthcheck Path** = `/health`.
Para avisos de caída, apunta un monitor externo gratuito (por ejemplo UptimeRobot) a
`https://TU-DOMINIO/health`.
