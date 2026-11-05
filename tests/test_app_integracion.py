"""Prueba de integración: carga el db.py y el app.py REALES con una conexión simulada.

No necesita PostgreSQL. Si psycopg2/bcrypt/pytz/barcode no están instaladas se
reemplazan por versiones mínimas; si lo están, se usan las reales.

    py -m unittest discover -s tests -v
"""
import datetime as dt
import os
import sys
import types
import unittest
from unittest import mock

RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, RAIZ)

os.environ.setdefault("DATABASE_URL", "postgresql://u:p@localhost:5432/prueba")
os.environ.setdefault("SECRET_KEY", "clave-de-prueba")
for v in ("RAILWAY_ENVIRONMENT",):
    os.environ.pop(v, None)


def _modulo(nombre, **attrs):
    m = types.ModuleType(nombre)
    m.__dict__.update(attrs)
    sys.modules[nombre] = m
    return m


def _stubs_si_faltan():
    try:
        import psycopg2  # noqa: F401
        import psycopg2.extras  # noqa: F401
        import psycopg2.pool  # noqa: F401
    except ImportError:
        _modulo("psycopg2", Binary=lambda x: x)
        _modulo("psycopg2.extras", DictCursor=object)
        _modulo("psycopg2.pool", ThreadedConnectionPool=object)
    try:
        import bcrypt  # noqa: F401
    except ImportError:
        _modulo("bcrypt", hashpw=lambda p, s: b"hash", gensalt=lambda: b"salt", checkpw=lambda p, h: True)
    try:
        import pytz  # noqa: F401
    except ImportError:
        class _UTC(dt.tzinfo):
            def utcoffset(self, d): return dt.timedelta(0)
            def dst(self, d): return dt.timedelta(0)
            def tzname(self, d): return "UTC"
            def localize(self, d): return d.replace(tzinfo=self)
        utc = _UTC()
        _modulo("pytz", UTC=utc, timezone=lambda n: utc)
    try:
        import barcode  # noqa: F401
        import barcode.writer  # noqa: F401
    except ImportError:
        _modulo("barcode", get_barcode_class=lambda n: None)
        _modulo("barcode.writer", SVGWriter=object)


class ConexionFalsa:
    """Registra el SQL ejecutado y responde con filas programadas."""

    def __init__(self, responder):
        self._responder = responder
        self.log = []

    def cursor(self):
        return CursorFalso(self)

    def commit(self): pass
    def rollback(self): pass
    def close(self): pass


class CursorFalso:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 1
        self._filas = []

    def execute(self, sql, params=None):
        sql = " ".join(str(sql).split())
        self.conn.log.append((sql, params))
        self._filas = self.conn._responder(sql, params)

    def fetchone(self):
        return self._filas[0] if self._filas else None

    def fetchall(self):
        return list(self._filas)

    def __iter__(self):
        return iter(self._filas)


HOY = dt.date(2026, 11, 5)
FILAS_EMPRESA = {}   # empresa_id -> fila de suscripción (la llena cada prueba)
NOMBRE_NUEVO = {"libre": False}
LOG = []             # todo el SQL ejecutado durante la prueba actual


def responder(sql, params):
    if "FROM empresas WHERE id = %s" in sql and "activa" in sql:
        fila = FILAS_EMPRESA.get(params[0])
        return [fila] if fila else []
    if sql.startswith("SELECT 1 FROM empresas WHERE nombre"):
        return [] if NOMBRE_NUEVO["libre"] else [(1,)]
    return [(1,)]


def fabricar_conexion():
    conn = ConexionFalsa(responder)
    LOG.append(conn.log)
    return conn


_stubs_si_faltan()
import db  # noqa: E402

db.conectar = fabricar_conexion
import app as appmod  # noqa: E402


def sql_ejecutado():
    return [item for log in LOG for item in log]


class IntegracionTest(unittest.TestCase):
    def setUp(self):
        LOG.clear()
        FILAS_EMPRESA.clear()
        FILAS_EMPRESA.update({
            1: {"activa": True, "fecha_vencimiento": None, "hoy": HOY},
            2: {"activa": True, "fecha_vencimiento": HOY - dt.timedelta(days=1), "hoy": HOY},
            3: {"activa": False, "fecha_vencimiento": None, "hoy": HOY},
        })
        NOMBRE_NUEVO["libre"] = False
        appmod.estado_empresa.invalidar()
        appmod.app.config["TESTING"] = True
        self.client = appmod.app.test_client()

    # ---------- utilidades
    def sesion(self, usuario="u", rol="admin", empresa_id=1):
        with self.client.session_transaction() as s:
            s["usuario"], s["rol"], s["empresa_id"] = usuario, rol, empresa_id
            s["_csrf"] = "tok"

    def post(self, ruta, **datos):
        datos.setdefault("csrf_token", "tok")
        return self.client.post(ruta, data=datos)

    def login_post(self, usuario_db):
        self.client.get("/")  # crea el token CSRF en la sesión
        with self.client.session_transaction() as s:
            token = s["_csrf"]
        with mock.patch.object(appmod, "validar_usuario", return_value=usuario_db), \
             mock.patch.object(appmod, "segundos_bloqueo_login", return_value=0), \
             mock.patch.object(appmod, "limpiar_intentos_login"), \
             mock.patch.object(appmod, "registrar_fallo_login"):
            return self.client.post("/", data={"usuario": "x", "password": "y", "csrf_token": token})

    # ---------- /health
    def test_health_ok(self):
        r = self.client.get("/health")
        self.assertEqual((r.status_code, r.get_json()), (200, {"status": "ok"}))

    def test_health_devuelve_503_si_la_base_falla(self):
        def romper():
            raise RuntimeError("sin base")
        with mock.patch.object(appmod, "conectar", romper):
            r = self.client.get("/health")
        self.assertEqual((r.status_code, r.get_json()), (503, {"status": "error"}))
        self.assertNotIn("sin base", r.get_data(as_text=True))

    # ---------- páginas legales
    def test_legales_sin_configurar_muestran_marcador(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for v in ("LEGAL_TITULAR", "LEGAL_DOCUMENTO", "LEGAL_EMAIL", "LEGAL_CIUDAD"):
                os.environ.pop(v, None)
            html = self.client.get("/terminos").get_data(as_text=True)
        self.assertIn("[COMPLETAR]", html)

    def test_legales_configuradas(self):
        entorno = {"LEGAL_TITULAR": "Steven SAS", "LEGAL_DOCUMENTO": "900123456-7",
                   "LEGAL_EMAIL": "soporte@stgestion.co", "LEGAL_CIUDAD": "Palmira"}
        with mock.patch.dict(os.environ, entorno):
            for ruta in ("/terminos", "/privacidad"):
                r = self.client.get(ruta)
                html = r.get_data(as_text=True)
                self.assertEqual(r.status_code, 200)
                self.assertIn("Steven SAS", html)
                self.assertIn("soporte@stgestion.co", html)
                self.assertNotIn("[COMPLETAR]", html)

    def test_pagina_de_login_enlaza_las_legales(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/terminos"', html)
        self.assertIn('href="/privacidad"', html)

    # ---------- login
    def test_login_de_empresa_vencida_es_rechazado(self):
        r = self.login_post({"usuario": "juan", "rol": "admin", "empresa_id": 2})
        self.assertEqual(r.status_code, 403)
        self.assertIn("venció el 04/11/2026", r.get_data(as_text=True))
        with self.client.session_transaction() as s:
            self.assertNotIn("usuario", s)

    def test_login_de_empresa_suspendida_es_rechazado(self):
        r = self.login_post({"usuario": "juan", "rol": "vendedor", "empresa_id": 3})
        self.assertEqual(r.status_code, 403)
        self.assertIn("suspendido", r.get_data(as_text=True))

    def test_login_de_empresa_al_dia_entra(self):
        r = self.login_post({"usuario": "ana", "rol": "admin", "empresa_id": 1})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/dashboard"))
        with self.client.session_transaction() as s:
            self.assertEqual(s["usuario"], "ana")

    def test_superadmin_entra_aunque_su_empresa_este_suspendida(self):
        FILAS_EMPRESA[1] = {"activa": False, "fecha_vencimiento": None, "hoy": HOY}
        r = self.login_post({"usuario": "superadmin", "rol": "owner_global", "empresa_id": 1})
        self.assertEqual(r.status_code, 302)

    def test_sesion_abierta_se_cierra_cuando_la_empresa_se_suspende(self):
        self.sesion(empresa_id=3)
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/?s=suspendida"))
        html = self.client.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("suspendido", html)
        with self.client.session_transaction() as s:
            self.assertNotIn("usuario", s)

    def test_parametro_s_desconocido_no_inyecta_texto(self):
        html = self.client.get("/?s=<script>alert(1)</script>").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)

    # ---------- rutas de administración de la suscripción
    def test_actualizar_suscripcion_guarda_los_valores(self):
        self.sesion(rol="owner_global")
        r = self.post("/empresa/2/suscripcion", plan="profesional",
                      fecha_vencimiento="2026-12-31", activa="1")
        self.assertEqual(r.status_code, 302)
        sql, params = [x for x in sql_ejecutado() if x[0].startswith("UPDATE empresas SET plan")][-1]
        self.assertEqual(params, ("profesional", dt.date(2026, 12, 31), True, 2))

    def test_actualizar_suscripcion_sin_checkbox_suspende_y_sin_fecha_no_vence(self):
        self.sesion(rol="owner_global")
        self.post("/empresa/2/suscripcion", plan="basico", fecha_vencimiento="")
        _, params = [x for x in sql_ejecutado() if x[0].startswith("UPDATE empresas SET plan")][-1]
        self.assertEqual(params, ("basico", None, False, 2))

    def test_actualizar_suscripcion_valida_entradas(self):
        self.sesion(rol="owner_global")
        self.assertEqual(self.post("/empresa/2/suscripcion", plan="gratis").status_code, 400)
        self.assertEqual(self.post("/empresa/2/suscripcion", plan="basico",
                                   fecha_vencimiento="31/12/2026").status_code, 400)
        self.assertFalse([x for x in sql_ejecutado() if x[0].startswith("UPDATE empresas SET plan")])

    def test_solo_el_superadmin_administra_suscripciones(self):
        self.sesion(rol="admin", empresa_id=1)
        self.assertEqual(self.post("/empresa/2/suscripcion", plan="basico").status_code, 403)
        self.assertEqual(self.post("/empresa/2/extender", dias="30").status_code, 403)
        self.assertFalse([x for x in sql_ejecutado() if x[0].startswith("UPDATE empresas")])

    def test_extender_suma_dias(self):
        self.sesion(rol="owner_global")
        r = self.post("/empresa/2/extender", dias="30")
        self.assertEqual(r.status_code, 302)
        sql, params = [x for x in sql_ejecutado() if x[0].startswith("UPDATE empresas SET fecha_vencimiento")][-1]
        self.assertEqual(params, (30, 2))
        self.assertIn("GREATEST", sql)

    def test_extender_valida_dias(self):
        self.sesion(rol="owner_global")
        for malo in ("0", "-5", "401", "abc", ""):
            self.assertEqual(self.post("/empresa/2/extender", dias=malo).status_code, 400, malo)
        self.assertFalse([x for x in sql_ejecutado() if x[0].startswith("UPDATE empresas SET fecha_vencimiento")])

    def test_pago_desbloquea_una_empresa_vencida(self):
        self.sesion(rol="owner_global")
        self.post("/empresa/2/extender", dias="30")
        # simula lo que haría la base: el vencimiento queda a futuro
        FILAS_EMPRESA[2] = {"activa": True, "fecha_vencimiento": HOY + dt.timedelta(days=30), "hoy": HOY}
        r = self.login_post({"usuario": "juan", "rol": "admin", "empresa_id": 2})
        self.assertEqual(r.status_code, 302)

    def test_crear_empresa_nace_con_prueba_de_14_dias(self):
        self.sesion(rol="owner_global")
        NOMBRE_NUEVO["libre"] = True
        r = self.post("/crear_empresa", nombre="  Pollos del Valle  ")
        self.assertEqual(r.status_code, 302)
        sql, params = [x for x in sql_ejecutado() if x[0].startswith("INSERT INTO empresas")][-1]
        self.assertEqual(params, ("Pollos del Valle", 14))
        self.assertIn("'prueba'", sql)

    def test_crear_empresa_duplicada_o_vacia_no_inserta(self):
        self.sesion(rol="owner_global")
        self.post("/crear_empresa", nombre="Ya Existe")          # el nombre ya existe
        NOMBRE_NUEVO["libre"] = True
        self.post("/crear_empresa", nombre="   ")                # vacío
        self.assertFalse([x for x in sql_ejecutado() if x[0].startswith("INSERT INTO empresas")])

    def test_rutas_nuevas_exigen_csrf(self):
        self.sesion(rol="owner_global")
        r = self.client.post("/empresa/2/extender", data={"dias": "30"})
        self.assertEqual(r.status_code, 403)

    # ---------- migración
    def test_la_migracion_agrega_las_columnas_sin_bloquear_empresas_existentes(self):
        conn = db.conectar()
        db.inicializar_db.__globals__["conectar"] = lambda: conn  # inicializar_db usa conectar() del módulo
        db.inicializar_db()
        sentencias = [s for s, _ in conn.log if s.startswith("ALTER TABLE empresas")]
        self.assertEqual(len(sentencias), 4)
        self.assertTrue(any("activa BOOLEAN NOT NULL DEFAULT TRUE" in s for s in sentencias))
        self.assertTrue(any("fecha_vencimiento DATE" in s and "NOT NULL" not in s and "DEFAULT" not in s
                            for s in sentencias))
        db.inicializar_db.__globals__["conectar"] = fabricar_conexion


if __name__ == "__main__":
    unittest.main()
