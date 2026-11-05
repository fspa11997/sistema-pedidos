"""Control de suscripción por empresa.

La lógica de decisión (``evaluar``) no toca la base de datos, así que se puede
probar sin PostgreSQL. ``EstadoEmpresa`` agrega una caché corta para no
consultar la base en cada petición, e ``instalar`` conecta todo a Flask.

Regla de fechas: ``fecha_vencimiento`` es el ÚLTIMO día con acceso (inclusive).
Una empresa sin fecha de vencimiento no vence nunca (es lo que reciben las
empresas que ya existían antes de esta migración).
"""
import threading
import time

from flask import redirect, request, session, url_for

AVISO_DIAS = 5          # días antes del vencimiento en que se muestra el aviso
CACHE_SEGUNDOS = 30     # cuánto se recuerda el estado de una empresa

# Rutas que funcionan aunque la empresa esté bloqueada (o sin sesión).
ENDPOINTS_LIBRES = frozenset({"login", "logout", "health", "terminos", "privacidad", "static"})

MENSAJES_LOGIN = {
    "suspendida": "El acceso de tu empresa está suspendido. Comunícate con el soporte para reactivarlo.",
    "vencida": "La suscripción de tu empresa está vencida. Comunícate con el soporte para renovarla.",
    "inexistente": "La empresa asociada a este usuario no existe. Comunícate con el soporte.",
}


def _resultado(estado, bloqueada, dias=None, mensaje=""):
    return {
        "estado": estado,
        "bloqueada": bloqueada,
        "dias_restantes": dias,
        "mensaje": mensaje,
    }


def evaluar(activa, fecha_vencimiento, hoy):
    """Decide el estado de una empresa. ``hoy`` es la fecha actual en Colombia."""
    if not activa:
        return _resultado("suspendida", True, None, MENSAJES_LOGIN["suspendida"])

    if fecha_vencimiento is None:
        return _resultado("al_dia", False)

    dias = (fecha_vencimiento - hoy).days

    if dias < 0:
        return _resultado(
            "vencida", True, dias,
            f"La suscripción de tu empresa venció el {fecha_vencimiento:%d/%m/%Y}. "
            "Comunícate con el soporte para renovarla.",
        )

    if dias <= AVISO_DIAS:
        if dias == 0:
            cuando = "vence hoy"
        elif dias == 1:
            cuando = "vence mañana"
        else:
            cuando = f"vence en {dias} días"
        return _resultado(
            "por_vencer", False, dias,
            f"La suscripción de tu empresa {cuando} ({fecha_vencimiento:%d/%m/%Y}). "
            "Renuévala para no perder el acceso.",
        )

    return _resultado("al_dia", False, dias)


def evaluar_fila(fila):
    """``fila`` es lo que devuelve db.leer_suscripcion_empresa (o None)."""
    if fila is None:
        return _resultado("inexistente", True, None, MENSAJES_LOGIN["inexistente"])
    return evaluar(fila["activa"], fila["fecha_vencimiento"], fila["hoy"])


class EstadoEmpresa:
    """Consulta el estado de una empresa con una caché de pocos segundos."""

    def __init__(self, leer_fila, segundos=CACHE_SEGUNDOS, reloj=time.monotonic):
        self._leer_fila = leer_fila
        self._segundos = segundos
        self._reloj = reloj
        self._cache = {}
        self._lock = threading.Lock()

    def obtener(self, empresa_id):
        if empresa_id is None:
            return evaluar_fila(None)

        ahora = self._reloj()
        with self._lock:
            guardado = self._cache.get(empresa_id)
        if guardado and ahora - guardado[0] < self._segundos:
            return guardado[1]

        resultado = evaluar_fila(self._leer_fila(empresa_id))
        with self._lock:
            self._cache[empresa_id] = (ahora, resultado)
        return resultado

    def invalidar(self, empresa_id=None):
        """Olvida una empresa (o todas). Solo afecta a este proceso."""
        with self._lock:
            if empresa_id is None:
                self._cache.clear()
            else:
                self._cache.pop(empresa_id, None)


def _aplica(sesion):
    """El superadmin global nunca se bloquea; sin sesión no hay nada que revisar."""
    return "usuario" in sesion and sesion.get("rol") != "owner_global"


def instalar(app, estado):
    """Registra el bloqueo por suscripción y el aviso de vencimiento en ``app``."""

    @app.before_request
    def verificar_suscripcion():
        if request.endpoint is None or request.endpoint in ENDPOINTS_LIBRES:
            return None
        if not _aplica(session):
            return None

        info = estado.obtener(session.get("empresa_id"))
        if info["bloqueada"]:
            session.clear()
            return redirect(url_for("login", s=info["estado"]))
        return None

    @app.context_processor
    def inyectar_aviso_suscripcion():
        if not _aplica(session):
            return {}
        info = estado.obtener(session.get("empresa_id"))
        aviso = info["mensaje"] if info["estado"] == "por_vencer" else None
        return {"aviso_suscripcion": aviso}
