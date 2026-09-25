@echo off
cd /d "%~dp0"
echo ============================================
echo  O2OA 10.0.2 镜像构建（仅需首次/升级时执行）
echo ============================================
docker compose build
echo.
echo [完成] 镜像 o2oa:10.0.2 已构建。
echo 接下来双击 start_o2oa.bat 启动服务。
pause
