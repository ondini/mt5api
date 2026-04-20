@echo off
echo Stopping and removing MT5 API services...
nssm stop   MT5API       2>nul
nssm remove MT5API       confirm 2>nul
nssm stop   MT5API-Nginx 2>nul
nssm remove MT5API-Nginx confirm 2>nul
echo Done.
pause
