#!/bin/bash
# 安装 launchd 每日定时任务（默认凌晨 3:00）
# 双击此文件即可安装

cd "$(dirname "$0")"
echo "========================================"
echo "  ⏰ 安装每日定时任务..."
echo "========================================"
echo ""

python3 organizer.py --install
EXIT_CODE=$?

SCHEDULE=$(python3 -c "import json; print(json.load(open('config.json')).get('schedule_time','03:00'))")

echo ""
echo "========================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "  ✅ 安装完成！每天 $SCHEDULE 自动整理"
else
    echo "  ❌ 安装失败，请检查上面错误信息"
fi
echo "========================================"
echo "按回车键关闭此窗口"
read -r
