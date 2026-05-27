from datetime import datetime, timezone
import pytz

UTC = timezone.utc
COLOMBIA = pytz.timezone("America/Bogota")

# 🔥 SIEMPRE guardar en base de datos
def ahora_utc():
    return datetime.now(UTC)

# 🔥 SOLO para mostrar en pantalla (frontend)
def a_colombia(dt):
    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    return dt.astimezone(COLOMBIA)