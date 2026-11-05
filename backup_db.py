"""Copia de seguridad de la base PostgreSQL (Railway) con pg_dump.

Uso (desde tu PC, con la URL PÚBLICA de la base en DATABASE_URL):

    py backup_db.py                  # crea respaldos/AAAA-MM-DD_HHMM.dump
    py backup_db.py --verificar      # además comprueba que el archivo se puede leer
    py backup_db.py --conservar 30   # cuántos respaldos guardar (por defecto 14)
    py backup_db.py --carpeta D:\\respaldos

Requiere tener instalado PostgreSQL client tools (pg_dump y pg_restore) y que
estén en el PATH. La versión de pg_dump debe ser igual o mayor a la del servidor.
Restaurar: ver RESPALDOS.md.
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def cargar_database_url():
    """Toma DATABASE_URL del entorno o de un config.env / .env junto al script."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    for nombre in ("config.env", ".env"):
        ruta = Path(__file__).resolve().parent / nombre
        if not ruta.is_file():
            continue
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea.startswith("DATABASE_URL="):
                valor = linea.split("=", 1)[1].strip().strip('"').strip("'")
                if valor:
                    return valor
    return None


def exigir_herramienta(nombre):
    ruta = shutil.which(nombre)
    if not ruta:
        sys.exit(
            f"No se encontró '{nombre}'. Instala las herramientas cliente de PostgreSQL "
            "(https://www.postgresql.org/download/) y agrega su carpeta bin al PATH."
        )
    return ruta


def main():
    ap = argparse.ArgumentParser(description="Respaldo de la base de datos con pg_dump")
    ap.add_argument("--carpeta", default="respaldos", help="carpeta de destino (por defecto: respaldos)")
    ap.add_argument("--conservar", type=int, default=14, help="cantidad de respaldos a conservar")
    ap.add_argument("--verificar", action="store_true", help="comprobar que el respaldo se puede leer")
    args = ap.parse_args()

    if args.conservar < 1:
        sys.exit("--conservar debe ser al menos 1")

    url = cargar_database_url()
    if not url:
        sys.exit("Falta DATABASE_URL (variable de entorno o config.env). Usa la URL PÚBLICA de Railway.")
    if ".railway.internal" in url:
        sys.exit("Esa es la URL interna de Railway: solo funciona dentro de Railway. "
                 "Usa DATABASE_PUBLIC_URL del servicio Postgres.")

    pg_dump = exigir_herramienta("pg_dump")
    carpeta = Path(args.carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)

    destino = carpeta / f"{datetime.now():%Y-%m-%d_%H%M}.dump"
    parcial = destino.with_suffix(".dump.parcial")

    # pg_dump acepta la URL de conexión completa en --dbname.
    comando = [pg_dump, "--dbname", url, "--format=custom", "--no-owner", "--no-acl",
               "--file", str(parcial)]

    print(f"Creando respaldo en {destino} ...")
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        parcial.unlink(missing_ok=True)
        sys.exit(f"pg_dump falló:\n{resultado.stderr.strip()}")

    parcial.replace(destino)
    print(f"Listo: {destino} ({destino.stat().st_size / 1024:.0f} KB)")

    if args.verificar:
        pg_restore = exigir_herramienta("pg_restore")
        comprobacion = subprocess.run([pg_restore, "--list", str(destino)], capture_output=True, text=True)
        if comprobacion.returncode != 0:
            sys.exit(f"El respaldo se creó pero no se pudo leer:\n{comprobacion.stderr.strip()}")
        tablas = sum(1 for l in comprobacion.stdout.splitlines() if " TABLE DATA " in l)
        print(f"Verificado: el archivo es legible y contiene datos de {tablas} tablas.")

    antiguos = sorted(carpeta.glob("*.dump"), reverse=True)[args.conservar:]
    for viejo in antiguos:
        viejo.unlink()
        print(f"Eliminado respaldo antiguo: {viejo.name}")


if __name__ == "__main__":
    main()
