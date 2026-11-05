"""Pruebas de la lógica de suscripción, sus hooks de Flask y las plantillas.

No necesitan PostgreSQL. Ejecutar desde la carpeta del proyecto:

    py -m unittest discover -s tests -v
"""
import os
import re
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, render_template, session
from jinja2 import Environment, FileSystemLoader

import suscripcion
from suscripcion import EstadoEmpresa, evaluar, evaluar_fila

RAIZ = os.path.join(os.path.dirname(__file__), "..")
HOY = date(2026, 11, 5)


class EvaluarTest(unittest.TestCase):
    def test_suspendida_siempre_bloquea(self):
        r = evaluar(False, HOY + timedelta(days=100), HOY)
        self.assertEqual((r["estado"], r["bloqueada"]), ("suspendida", True))

    def test_sin_vencimiento_no_vence_nunca(self):
        r = evaluar(True, None, HOY)
        self.assertEqual((r["estado"], r["bloqueada"], r["dias_restantes"]), ("al_dia", False, None))

    def test_el_dia_de_vencimiento_todavia_tiene_acceso(self):
        r = evaluar(True, HOY, HOY)
        self.assertFalse(r["bloqueada"])
        self.assertEqual(r["estado"], "por_vencer")
        self.assertIn("vence hoy", r["mensaje"])

    def test_un_dia_despues_queda_vencida(self):
        r = evaluar(True, HOY - timedelta(days=1), HOY)
        self.assertEqual((r["estado"], r["bloqueada"], r["dias_restantes"]), ("vencida", True, -1))
        self.assertIn("04/11/2026", r["mensaje"])

    def test_aviso_dentro_de_los_ultimos_dias(self):
        r = evaluar(True, HOY + timedelta(days=suscripcion.AVISO_DIAS), HOY)
        self.assertEqual(r["estado"], "por_vencer")
        r = evaluar(True, HOY + timedelta(days=suscripcion.AVISO_DIAS + 1), HOY)
        self.assertEqual(r["estado"], "al_dia")

    def test_mensajes_de_uno_y_varios_dias(self):
        self.assertIn("vence mañana", evaluar(True, HOY + timedelta(days=1), HOY)["mensaje"])
        self.assertIn("vence en 3 días", evaluar(True, HOY + timedelta(days=3), HOY)["mensaje"])

    def test_empresa_inexistente_bloquea(self):
        r = evaluar_fila(None)
        self.assertEqual((r["estado"], r["bloqueada"]), ("inexistente", True))

    def test_evaluar_fila_lee_las_columnas(self):
        fila = {"activa": True, "fecha_vencimiento": HOY - timedelta(days=3), "hoy": HOY}
        self.assertEqual(evaluar_fila(fila)["estado"], "vencida")


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.t = [0.0]
        self.lecturas = []
        self.fila = {"activa": True, "fecha_vencimiento": None, "hoy": HOY}

        def leer(empresa_id):
            self.lecturas.append(empresa_id)
            return self.fila

        self.estado = EstadoEmpresa(leer, segundos=30, reloj=lambda: self.t[0])

    def test_usa_cache_y_expira(self):
        self.estado.obtener(1)
        self.estado.obtener(1)
        self.assertEqual(self.lecturas, [1])
        self.t[0] = 31
        self.estado.obtener(1)
        self.assertEqual(self.lecturas, [1, 1])

    def test_invalidar_fuerza_nueva_lectura(self):
        self.assertFalse(self.estado.obtener(1)["bloqueada"])
        self.fila = {"activa": False, "fecha_vencimiento": None, "hoy": HOY}
        self.assertFalse(self.estado.obtener(1)["bloqueada"])  # sigue en caché
        self.estado.invalidar(1)
        self.assertTrue(self.estado.obtener(1)["bloqueada"])

    def test_empresa_none_no_consulta_la_base(self):
        self.assertTrue(self.estado.obtener(None)["bloqueada"])
        self.assertEqual(self.lecturas, [])

    def test_cada_empresa_se_cachea_por_separado(self):
        self.estado.obtener(1)
        self.estado.obtener(2)
        self.assertEqual(self.lecturas, [1, 2])


def crear_app_de_prueba(filas):
    """App mínima con los mismos endpoints que usa la real."""
    app = Flask(__name__, template_folder=os.path.join(RAIZ, "templates"),
                static_folder=os.path.join(RAIZ, "static"))
    app.secret_key = "test"
    estado = EstadoEmpresa(lambda eid: filas.get(eid), segundos=0)
    suscripcion.instalar(app, estado)

    @app.route("/")
    def login():
        return "login"

    @app.route("/logout")
    def logout():
        return "logout"

    @app.route("/health")
    def health():
        return "ok"

    @app.route("/terminos")
    def terminos():
        return render_template("terminos.html", titular="ACME SAS", documento="900.1", email="a@b.co",
                               ciudad="Cali", actualizado="hoy")

    @app.route("/privacidad")
    def privacidad():
        return render_template("privacidad.html", titular="ACME SAS", documento="900.1", email="a@b.co",
                               ciudad="Cali", actualizado="hoy")

    @app.route("/ventas")
    def ventas():
        return "ventas ok"

    return app


class HooksTest(unittest.TestCase):
    def setUp(self):
        self.filas = {
            1: {"activa": True, "fecha_vencimiento": None, "hoy": HOY},
            2: {"activa": True, "fecha_vencimiento": HOY - timedelta(days=1), "hoy": HOY},
            3: {"activa": False, "fecha_vencimiento": None, "hoy": HOY},
            4: {"activa": True, "fecha_vencimiento": HOY + timedelta(days=2), "hoy": HOY},
        }
        self.app = crear_app_de_prueba(self.filas)
        self.client = self.app.test_client()

    def entrar(self, empresa_id, rol="admin"):
        with self.client.session_transaction() as s:
            s["usuario"] = "u"
            s["rol"] = rol
            s["empresa_id"] = empresa_id

    def test_empresa_al_dia_pasa(self):
        self.entrar(1)
        self.assertEqual(self.client.get("/ventas").status_code, 200)

    def test_empresa_vencida_se_redirige_y_se_cierra_la_sesion(self):
        self.entrar(2)
        r = self.client.get("/ventas")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/?s=vencida"))
        with self.client.session_transaction() as s:
            self.assertNotIn("usuario", s)

    def test_empresa_suspendida(self):
        self.entrar(3)
        r = self.client.get("/ventas")
        self.assertTrue(r.headers["Location"].endswith("/?s=suspendida"))

    def test_empresa_borrada(self):
        self.entrar(99)
        r = self.client.get("/ventas")
        self.assertTrue(r.headers["Location"].endswith("/?s=inexistente"))

    def test_owner_global_nunca_se_bloquea(self):
        self.entrar(3, rol="owner_global")
        self.assertEqual(self.client.get("/ventas").status_code, 200)

    def test_sin_sesion_no_interfiere(self):
        self.assertEqual(self.client.get("/ventas").status_code, 200)

    def test_rutas_libres_funcionan_con_empresa_bloqueada(self):
        self.entrar(2)
        for ruta in ("/", "/health", "/terminos", "/privacidad", "/logout"):
            self.assertEqual(self.client.get(ruta).status_code, 200, ruta)

    def test_archivos_estaticos_siguen_disponibles(self):
        self.entrar(2)
        r = self.client.get("/static/style.css")
        self.assertEqual(r.status_code, 200)
        r.close()

    def test_un_pago_desbloquea_en_la_siguiente_peticion(self):
        self.entrar(2)
        self.assertEqual(self.client.get("/ventas").status_code, 302)
        self.filas[2] = {"activa": True, "fecha_vencimiento": HOY + timedelta(days=30), "hoy": HOY}
        self.entrar(2)
        self.assertEqual(self.client.get("/ventas").status_code, 200)

    def test_aviso_de_vencimiento_llega_a_las_plantillas(self):
        ctx = self.app.test_request_context("/")
        ctx.push()
        try:
            session["usuario"], session["rol"], session["empresa_id"] = "u", "admin", 4
            contexto = {}
            for f in self.app.template_context_processors[None]:
                contexto.update(f())
            self.assertIn("vence en 2 días", contexto["aviso_suscripcion"])
            session["empresa_id"] = 1
            contexto = {}
            for f in self.app.template_context_processors[None]:
                contexto.update(f())
            self.assertIsNone(contexto["aviso_suscripcion"])
        finally:
            ctx.pop()


class PlantillasTest(unittest.TestCase):
    def setUp(self):
        self.app = crear_app_de_prueba({})
        self.client = self.app.test_client()

    def test_paginas_legales_muestran_los_datos_del_titular(self):
        for ruta in ("/terminos", "/privacidad"):
            html = self.client.get(ruta).get_data(as_text=True)
            self.assertIn("ACME SAS", html)
            self.assertIn("a@b.co", html)
            self.assertNotIn("{{", html)
        self.assertIn("no reemplazan la factura electrónica", self.client.get("/terminos").get_data(as_text=True))
        self.assertIn("Ley 1581 de 2012", self.client.get("/privacidad").get_data(as_text=True))

    def test_panel_de_empresas_del_dashboard(self):
        """Renderiza el bloque real del panel de empresas con una empresa en cada estado."""
        with open(os.path.join(RAIZ, "templates", "dashboard.html"), encoding="utf-8") as f:
            fuente = f.read()
        ini = fuente.index("<!-- 🔵 CREAR EMPRESA -->")
        fin = fuente.index("<!-- 📦 FORMULARIO PEDIDOS -->", ini)
        # se quita el {% endif %} final, que cierra el if owner_global de fuera del bloque
        bloque = fuente[ini:fin].rstrip()
        assert bloque.endswith("{% endif %}")
        bloque = bloque[: -len("{% endif %}")]

        env = Environment(loader=FileSystemLoader(os.path.join(RAIZ, "templates")))
        env.globals["csrf_token"] = lambda: "TOK"
        html = env.from_string(bloque).render(
            planes=("prueba", "basico", "profesional"),
            empresas_suscripcion=[
                {"id": 1, "nombre": "Al Dia SAS", "plan": "basico", "activa": True,
                 "fecha_vencimiento": date(2027, 1, 31), "estado": "al_dia", "dias": 87},
                {"id": 2, "nombre": "Vieja SAS", "plan": "prueba", "activa": True,
                 "fecha_vencimiento": date(2026, 11, 1), "estado": "vencida", "dias": -4},
                {"id": 3, "nombre": "Suspendida SAS", "plan": "pro", "activa": False,
                 "fecha_vencimiento": None, "estado": "suspendida", "dias": None},
                {"id": 4, "nombre": "Casi SAS", "plan": "basico", "activa": True,
                 "fecha_vencimiento": date(2026, 11, 7), "estado": "por_vencer", "dias": 2},
                {"id": 5, "nombre": "Libre SAS", "plan": "basico", "activa": True,
                 "fecha_vencimiento": None, "estado": "al_dia", "dias": None},
            ],
        )
        self.assertIn("hace 4 días", html)
        self.assertIn("Suspendida", html)
        self.assertIn("Por vencer", html)
        self.assertIn("sin vencimiento", html)
        self.assertIn('value="2027-01-31"', html)
        self.assertIn('action="/empresa/2/extender"', html)
        self.assertIn('action="/empresa/3/suscripcion"', html)
        # el interruptor de acceso solo viene marcado en las empresas activas
        self.assertEqual(html.count("checked"), 4)
        # todos los formularios POST llevan token CSRF
        self.assertEqual(html.count("<form"), html.count('name="csrf_token"'))

    def test_login_enlaza_terminos_y_privacidad(self):
        env = Environment(loader=FileSystemLoader(os.path.join(RAIZ, "templates")))
        env.globals.update(csrf_token=lambda: "T", url_for=lambda e, **k: f"/{e}" + (f"/{k['filename']}" if k else ""))
        html = env.get_template("login.html").render(error=None)
        self.assertIn('href="/terminos"', html)
        self.assertIn('href="/privacidad"', html)


if __name__ == "__main__":
    unittest.main()
