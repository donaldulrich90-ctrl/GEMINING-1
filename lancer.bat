@echo off
REM Lancement local de GOOD ENGINEERS OS (Django) sous Windows
cd /d "%~dp0"
echo Installation des dependances...
pip install -r requirements.txt
echo.
echo Demarrage du serveur sur http://localhost:8000/
echo Compte de test : admin / admin
python manage.py runserver 0.0.0.0:8000
pause
