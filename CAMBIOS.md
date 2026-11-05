# Cambios: suscripciones, respaldos, health check y legales

## Cómo aplicarlos
Copia los archivos de este zip sobre tu proyecto (respetando carpetas) y haz commit/push.
Railway redespliega solo. También sirve `git apply cambios.patch` desde la raíz del repo.
La migración de base de datos es automática al arrancar (solo agrega columnas).

## Después de desplegar (en este orden)
1. Railway > servicio web > Variables: `LEGAL_TITULAR`, `LEGAL_DOCUMENTO`, `LEGAL_EMAIL`, `LEGAL_CIUDAD`.
2. Railway > servicio web > Settings > Deploy > Healthcheck Path = `/health`.
3. Railway > servicio Postgres > Backups: activa respaldos si tu plan los incluye, y programa `backup_db.py` (ver RESPALDOS.md).
4. Entra como superadmin > panel de empresas: las empresas existentes quedan **sin vencimiento**; ponles plan y fecha cuando quieras empezar a cobrar.
5. Haz revisar `terminos.html` y `privacidad.html` por un abogado. Son un borrador razonable, no asesoría legal. Revisa en especial: 30 días de conservación tras vencer y tope de responsabilidad de 3 meses.

## Qué cambió
- `suscripcion.py` (nuevo): reglas de bloqueo, caché de 30 s y hooks de Flask.
- `db.py`: columnas `plan`, `activa`, `fecha_vencimiento`, `notas` en `empresas` + funciones para leer/fijar/extender la suscripción.
- `app.py`: login rechaza empresas suspendidas/vencidas; sesiones abiertas se cierran; rutas `/empresa/<id>/suscripcion` y `/empresa/<id>/extender`; `/health`; `/terminos` y `/privacidad`; empresas nuevas nacen con 14 días de prueba; solo el superadmin carga la lista de empresas.
- `templates/dashboard.html`: panel de empresas con estado, plan, vencimiento, interruptor de acceso y "Registrar pago"; aviso de vencimiento 5 días antes.
- `templates/login.html`: enlaces a términos y privacidad. Nuevas: `terminos.html`, `privacidad.html`, `legal_base.html`.
- `backup_db.py` + `RESPALDOS.md`: respaldo con pg_dump, verificación, rotación y guía de restauración.
- `tests/`: 47 pruebas (`py -m unittest discover -s tests -v`).
- README, `README_GENERAR_EXE.txt`, `.gitignore`, `Gestion.spec`: documentación y advertencia de no entregar el .exe.

## Lo que NO se hizo (a propósito)
- Dinero de `REAL` a `NUMERIC`: psycopg2 devolvería `Decimal` y mezclarlo con `float` rompería cálculos en ~2.000 líneas. Hacerlo bien requiere una base de pruebas con Postgres real.
- Dividir `app.py` en módulos.
- Registro propio de clientes y pasarela de pagos.
- Facturación electrónica DIAN (requiere proveedor tecnológico).
- Fotos fuera de la base de datos.
