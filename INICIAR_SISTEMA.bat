@echo off
setlocal
cd /d "%~dp0"
title IVA SV - Iniciar sistema

echo ==============================================
echo              IVA SV - INICIANDO
echo ==============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro Python instalado.
    echo Instala Python 3.11 o superior y vuelve a ejecutar este archivo.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Primera ejecucion: preparando el sistema...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

python -c "import streamlit, sqlalchemy, psycopg, pandas, openpyxl, reportlab" >nul 2>&1
if errorlevel 1 (
    echo Instalando componentes necesarios. Esto solo ocurre la primera vez...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] No se pudieron instalar los componentes.
        echo Revisa tu conexion a Internet y vuelve a intentarlo.
        pause
        exit /b 1
    )
)

if not defined APP_USER set APP_USER=admin
if not defined APP_PASSWORD set APP_PASSWORD=cambiarme

echo.
echo Sistema listo.
echo Usuario local: admin
echo Contrasena local: cambiarme
echo.
echo Se abrira en tu navegador en unos segundos...
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8501"

python -m streamlit run app.py --server.port 8501

endlocal
