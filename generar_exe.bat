@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo   GESTION - GENERAR Gestion.exe
echo ========================================
echo.

REM Buscar el lanzador de Python de Windows (py) o python.
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo ERROR: No se encontro Python en Windows.
        echo.
        echo Instala Python 3.11+ y marca "Add Python to PATH".
        echo Luego vuelve a ejecutar este archivo.
        pause
        exit /b 1
    )
)

echo Python detectado: %PY%
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creando entorno virtual...
    %PY% -m venv .venv
    if errorlevel 1 goto :error
) else (
    echo [1/4] Entorno virtual ya existe.
)

echo [2/4] Actualizando pip e instalando dependencias...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo [3/4] Generando Gestion.exe...
echo     (El proceso de compilacion se ejecuta fuera de OneDrive para evitar bloqueos de archivos)
.venv\Scripts\python.exe -m PyInstaller --noconfirm --workpath "%TEMP%\GestionBuild_%RANDOM%" --distpath "%~dp0dist" Gestion.spec
if errorlevel 1 goto :error

echo.
echo [4/4] Proceso terminado.
echo.
echo ========================================
echo   LISTO
echo   Ejecutable: dist\Gestion.exe
echo ========================================
echo.
echo Para abrirlo: doble clic en dist\Gestion.exe
echo.
pause
exit /b 0

:error
echo.
echo ========================================
echo   ERROR AL GENERAR EL EJECUTABLE
echo ========================================
echo Revisa el mensaje anterior.
pause
exit /b 1
