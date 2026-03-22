@echo off
setlocal
cd /d "%~dp0backend"
if not exist "requirements.txt" (
  echo ERROR: Run this from the attendance-predictor folder. Missing backend\requirements.txt
  exit /b 1
)
pip install -r requirements.txt
python model\train_model.py
exit /b %ERRORLEVEL%
