@echo off
rem =============================================================
rem  文件: run.bat
rem  用途: OJ 开发环境一键启动脚本（Windows）
rem  流程: 1) 启动基础设施容器(postgres/redis/judge-node)
rem        2) 新窗口启动后端 API (:8000)
rem        3) 新窗口启动前端 Vite (:5173)
rem  用法: 双击或在根目录执行 run.bat；stop 参数可停掉容器
rem =============================================================
chcp 65001 >nul
title OJ Dev Launcher

if "%1"=="stop" goto :stop

rem 密钥文件检查（缺失时提示按模板创建，避免 compose 启动失败）
set "MISSING_ENV="
if not exist "%~dp0deploy\api.env"        set "MISSING_ENV=deploy\api.env"
if not exist "%~dp0deploy\judge-node.env" set "MISSING_ENV=%MISSING_ENV% deploy\judge-node.env"
if not exist "%~dp0deploy\.env"           set "MISSING_ENV=%MISSING_ENV% deploy\.env"
if defined MISSING_ENV (
    echo [错误] 缺少密钥文件: %MISSING_ENV%
    echo   请复制 deploy\api.env.example 为 deploy\api.env 并填好值；
    echo   deploy\judge-node.env 内容一行: SERVER_TOKEN=dev-judge-token
    echo   deploy\.env 至少含: ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL / SERVER_TOKEN=dev-assistant-token
    pause
    exit /b 1
)

echo [1/3] 启动基础设施容器 (postgres / redis / judge-node)...
docker compose -f "%~dp0deploy\docker-compose.yml" up -d
if errorlevel 1 (
    echo [错误] docker compose 启动失败，请确认 Docker Desktop 已运行
    pause
    exit /b 1
)

echo [2/3] 启动后端 API (:8000)...
if not exist "%~dp0api\.venv\Scripts\uvicorn.exe" (
    echo [提示] api 虚拟环境不存在，先执行: cd api ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -e .
    pause
    exit /b 1
)
start "OJ API" cmd /k "cd /d %~dp0api && .venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [3/3] 启动前端 (:5173)...
if not exist "%~dp0web\node_modules" (
    echo [提示] 前端依赖未安装，先执行: cd web ^&^& npm install
    pause
    exit /b 1
)
start "OJ Web" cmd /k "cd /d %~dp0web && npm run dev"

echo.
echo ============================================
echo   API      http://localhost:8000/health
echo   前端     http://localhost:5173
echo   判题节点 docker 容器自动外连 :50051
echo ============================================
echo 两个子窗口可最小化；停止服务请运行: run.bat stop
echo.
pause
exit /b 0

:stop
echo 停止基础设施容器...
docker compose -f "%~dp0deploy\docker-compose.yml" stop
echo 提示: API 与前端窗口请直接关闭对应的 cmd 窗口
pause
