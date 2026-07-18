from datetime import datetime, timezone
import pytz

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