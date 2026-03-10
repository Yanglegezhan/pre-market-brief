@echo off
chcp 65001 >nul
echo ========================================
echo 新闻筛选系统 - 手动运行
echo ========================================
echo.

cd /d "%~dp0"

:: 检查参数
if "%1"=="" goto :menu
if "%1"=="test" goto :run_test
if "%1"=="filter" goto :run_filter
if "%1"=="brief" goto :run_brief
goto :menu

:menu
echo 请选择运行模式:
echo.
echo 1. 新闻筛选模式 (--news-filter --test)
echo 2. 新闻筛选模式 (--news-filter, 推送飞书)
echo 3. 盘前简报模式 (--test)
echo 4. 盘前简报模式 (推送飞书)
echo 5. 退出
echo.
set /p choice=请输入选项 (1-5):

if "%choice%"=="1" goto :run_test
if "%choice%"=="2" goto :run_filter
if "%choice%"=="3" goto :run_brief_test
if "%choice%"=="4" goto :run_brief
if "%choice%"=="5" exit /b 0
goto :menu

:run_test
echo.
echo [新闻筛选模式 - 测试运行]
echo 采集昨日15:00之后的新闻并分析...
echo.
python main.py --news-filter --test
echo.
echo 报告已保存到当前目录
echo.
pause
goto :menu

:run_filter
echo.
echo [新闻筛选模式 - 正式运行]
echo 采集昨日15:00之后的新闻，分析并推送飞书...
echo.
python main.py --news-filter
echo.
pause
goto :menu

:run_brief_test
echo.
echo [盘前简报模式 - 测试运行]
echo 采集盘前市场数据并生成简报...
echo.
python main.py --test
echo.
pause
goto :menu

:run_brief
echo.
echo [盘前简报模式 - 正式运行]
echo 采集盘前市场数据，生成简报并推送飞书...
echo.
python main.py
echo.
pause
goto :menu
