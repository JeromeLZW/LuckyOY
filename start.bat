@echo off
chcp 65001 >nul
title 1688工厂搜索看板服务
echo ============================================================
echo   1688 源头工厂推荐看板
echo   启动后端服务中...
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/2] 启动API服务 (端口 5688)...
start /b python server.py

echo [2/2] 等待服务就绪...
timeout /t 3 /nobreak >nul

echo.
echo   服务已启动！正在打开浏览器...
echo   访问地址: http://localhost:5688
echo.
echo   按 Ctrl+C 停止服务
echo ============================================================

start http://localhost:5688

python server.py
