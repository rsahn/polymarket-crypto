@echo off
cd /d C:\Users\Ramy\Documents\polymarket-crypto
set PYTHONPATH=C:\Users\Ramy\Documents\polymarket-crypto
set PATH=C:\Users\Ramy\AppData\Local\Programs\Python\Python313;%PATH%
python -m analysis.d6.real_execution_calibration_v1.multi_runner --simulate > D:\polymarket-real-calibration\live\sim_v2.log 2>&1
