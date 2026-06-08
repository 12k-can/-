#!/bin/bash
# 卸载 launchd 每日定时任务
# 双击此文件即可移除

cd "$(dirname "$0")"
echo "========================================"
echo "  🗑️  卸载每日定时任务..."
echo "========================================"
echo ""

python3 organizer.py --uninstall
EXIT_CODE=$?

echo ""
echo "========================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "  ✅ 已卸载！不会再自动整理了"
else
    echo "  ❌ 卸载失败，请检查上面错误信息"
fi
echo "========================================"
echo "按回车键关闭此窗口"
read -r
