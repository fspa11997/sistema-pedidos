COMO GENERAR Gestion.exe
========================

1. Descomprime este proyecto en Windows.
2. Abre la carpeta Gestion-main.
3. Haz doble clic en:

   generar_exe.bat

El archivo se encarga de crear el entorno virtual, instalar las dependencias y ejecutar PyInstaller.

El ejecutable quedara en:

   dist\Gestion\Gestion.exe

IMPORTANTE
----------
- Cada vez que hagas cambios en app.py, db.py, templates o static, vuelve a ejecutar generar_exe.bat.
- La base de datos pedidos.db se mantiene junto al Gestion.exe para que los datos no dependan de la carpeta temporal de PyInstaller.
- Si Windows indica que Python no existe, instala Python 3.11 o superior y activa "Add Python to PATH" durante la instalacion.
