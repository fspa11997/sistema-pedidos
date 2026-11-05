COMO GENERAR Gestion.exe
========================

1. Descomprime este proyecto en Windows (mejor fuera de OneDrive).
2. Haz doble clic en:  generar_exe.bat
   (crea el entorno virtual, instala dependencias y ejecuta PyInstaller)
3. El ejecutable queda en:  dist\Gestion.exe

USAR EL EJECUTABLE
------------------
- La primera vez que abras Gestion.exe se crea "config.env" junto al .exe y se
  abre en el Bloc de notas. Pega tu DATABASE_URL (PostgreSQL de Railway),
  guarda y vuelve a abrir Gestion.exe.
- Se abrira el navegador en http://127.0.0.1:5000/
- Si algo falla, aparece una ventana con el motivo y el detalle queda en
  "gestion.log" (junto al .exe).
- Para copiar el programa a otro PC basta con llevar Gestion.exe y config.env.

IMPORTANTE
----------
- SOLO USO INTERNO: Gestion.exe + config.env dan acceso directo a TODA la base
  de datos (todas las empresas). No se lo entregues a clientes; ellos deben usar
  la aplicacion web.
- La app usa PostgreSQL (ya no SQLite). No hace falta pedidos.db.
- Cada vez que cambies app.py, db.py, templates o static, vuelve a ejecutar
  generar_exe.bat.
- Usa Python 3.11 a 3.13 de 64 bits.
