@ECHO OFF
cd /d "%~dp0"

SET "VENV_DIR=%~dp0venv"
SET "APP_PORT=5000"

IF EXIST "%~dp0.env" (
    FOR /F "usebackq tokens=1,* delims==" %%A IN ("%~dp0.env") DO (
        IF /I "%%A"=="FLASK_PORT" SET "APP_PORT=%%B"
    )
)

IF NOT EXIST "%VENV_DIR%\Scripts\python.exe" (
    ECHO Criando ambiente virtual em venv...
    python -m venv "%VENV_DIR%"
    IF ERRORLEVEL 1 (
        ECHO Falha ao criar o venv. Verifique se o Python esta instalado.
        PAUSE
        EXIT /B 1
    )
)

CALL "%VENV_DIR%\Scripts\activate.bat"
IF ERRORLEVEL 1 (
    ECHO Falha ao ativar o venv.
    PAUSE
    EXIT /B 1
)

ECHO Instalando/atualizando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
IF ERRORLEVEL 1 (
    ECHO Falha ao instalar dependencias.
    PAUSE
    EXIT /B 1
)

ECHO.
ECHO Iniciando Conferencia SIB/ANS...
ECHO Abrindo http://127.0.0.1:%APP_PORT%/ no navegador...
START "" CMD /C "TIMEOUT /T 2 /NOBREAK >NUL & START http://127.0.0.1:%APP_PORT%/"
python app.py
PAUSE
