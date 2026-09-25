@echo off
chcp 65001 >nul
cd /d "%~dp0"
title O2OA 10.0.2 一键启动

echo ============================================
echo  O2OA 10.0.2 + MySQL 一键启动
echo ============================================
echo.

docker compose up -d
echo.

echo [1/3] 等待容器就绪（ARM64+QEMU 约 5-8 分钟）...
set _t=0
:waitloop
timeout /t 5 /nobreak >nul
curl -s -o nul --max-time 3 http://localhost:9090/ >nul 2>nul
if %errorlevel%==0 goto ready
set /a _t+=5
if %_t% lss 480 goto waitloop

echo       [警告] 超时仍未就绪，请手动检查 http://localhost:9090
goto netlock

:ready
echo       容器已就绪，用时 %_t% 秒
echo.

:netlock
echo [2/3] 重新施加封网规则（断 O2OA 与 o2oa.net）...
echo       Docker 重启后 iptables 规则会丢失，此处自动补回。
echo.
where bash >nul 2>nul
if errorlevel 1 (
  echo [警告] 未找到 bash，请手动运行 netlock_o2oa.bat
) else (
  bash ./o2oa_netlock.sh
)

echo.
echo [3/3] 拉起 AI 侧（本地推理后端 + 适配网关 + OCR）...
echo       幂等：已在运行的组件会自动跳过。
echo.
if exist "gateway\start_ai_watchdog.bat" (
  call "gateway\start_ai_watchdog.bat"
  echo       AI 侧以「常驻看门狗」方式拉起：掉线会自动重启，无需手动干预。
) else (
  echo       [警告] 缺少 gateway\start_ai_watchdog.bat，跳过
)
echo.
echo ============================================
echo  [完成]
echo    访问地址: http://localhost:9090
echo    查看日志: docker compose logs -f o2oa
echo    停止服务: stop_o2oa.bat
echo    封网自检: bash o2oa_netlock.sh --check
echo    AI 自检 : gateway\start_ai_stack.bat /v
echo    AI 看门狗日志: gateway\watchdog.log
echo ============================================
pause
