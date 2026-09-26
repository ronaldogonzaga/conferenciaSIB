@ECHO OFF
cd /d "%~dp0"

SET "VENV_DIR=%~dp0venv"

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
python app.py
PAUSE
