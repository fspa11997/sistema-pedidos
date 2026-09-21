# Lanzador automático para el EXE. No modifica app.py.
import threading
import time
import webbrowser
import urllib.request

URL = "http://127.0.0.1:5000/"

def abrir_cuando_este_listo():
    for _ in range(60):
        try:
            urllib.request.urlopen(URL, timeout=0.4)
            webbrowser.open(URL)
            return
        except Exception:
            time.sleep(0.25)

threading.Thread(target=abrir_cuando_este_listo, daemon=True).start()
