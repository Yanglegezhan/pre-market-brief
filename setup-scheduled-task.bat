@echo off
chcp 65001 >nul
echo ========================================
echo 新闻筛选系统 - Windows定时任务设置
echo ========================================
echo.

:: 设置项目路径
set "PROJECT_PATH=%~dp0"
cd /d "%PROJECT_PATH%"

echo 项目路径: %PROJECT_PATH%
echo.

:: 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请确保Python已安装并添加到PATH
    pause
    exit /b 1
)

echo [1/3] Python已安装

:: 检查依赖
echo [2/3] 检查依赖...
pip show requests >nul 2>&1
if errorlevel 1 (
    echo 安装依赖...
    pip install -r requirements.txt
)

echo [3/3] 依赖检查完成
echo.

:: 创建计划任务
echo 正在创建定时任务（每天8:30运行）...

:: 删除旧任务（如果存在）
schtasks /delete /tn "NewsFilter-Daily" /f >nul 2>&1

:: 创建新任务 - 每天8:30运行
schtasks /create ^
    /tn "NewsFilter-Daily" ^
    /tr "python.exe %PROJECT_PATH%main.py --news-filter" ^
    /sc daily ^
    /st 08:30 ^
    /ru SYSTEM ^
    /np ^
    /rl HIGHEST ^
    /f

if errorlevel 1 (
    echo [错误] 创建定时任务失败，请尝试以管理员身份运行
    pause
    exit /b 1
)

echo.
echo ========================================
echo 定时任务创建成功！
echo ========================================
echo 任务名称: NewsFilter-Daily
echo 运行时间: 每天 08:30
echo 运行命令: python main.py --news-filter
echo.
echo 管理命令:
echo   查看任务: schtasks /query /tn "NewsFilter-Daily"
echo   删除任务: schtasks /delete /tn "NewsFilter-Daily" /f
echo   手动运行: schtasks /run /tn "NewsFilter-Daily"
echo.
echo 按任意键退出...
pause >nul
