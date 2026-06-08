#!/usr/bin/env python3
"""
macOS 桌面文件自动整理工具

用法：
    python organizer.py --run          # 立即执行一次整理
    python organizer.py --install      # 安装 launchd 定时任务 (每天 03:00)
    python organizer.py --uninstall    # 卸载 launchd 定时任务
    python organizer.py --status       # 查看定时任务状态
    python organizer.py --show-config  # 打印当前配置
"""

import argparse
import json
import logging
import os
import plistlib
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────────────────────

SCRIPT_NAME = "com.user.dailyorganizer"
CONFIG_FILE_NAME = "config.json"
DEFAULT_LOG_DIR = "~/Library/Logs/DesktopOrganizer"

# macOS 系统文件（忽略不处理）
SYSTEM_FILES = frozenset({
    ".DS_Store",
    "Thumbs.db",
    ".localized",
    ".Spotlight-V100",
    ".Trashes",
    ".fseventsd",
    "desktop.ini",
})

# ── 配置管理 ──────────────────────────────────────────────────────────


def get_script_dir() -> Path:
    """返回 organizer.py 所在目录（用于定位 config.json 等伴生文件）。"""
    return Path(__file__).parent.resolve()


def get_config_path() -> Path:
    return get_script_dir() / CONFIG_FILE_NAME


def get_default_config() -> dict:
    return {
        "folders": ["~/Desktop"],
        "schedule_time": "03:00",
        "enable_logging": True,
        "log_directory": DEFAULT_LOG_DIR,
        "rules": {
            "图片": [
                ".jpg", ".jpeg", ".png", ".gif", ".bmp",
                ".svg", ".webp", ".heic", ".tiff",
            ],
            "文档": [
                ".pdf", ".doc", ".docx", ".xls", ".xlsx",
                ".ppt", ".pptx", ".txt", ".md", ".csv",
                ".pages", ".numbers", ".key",
            ],
            "视频": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"],
            "压缩包": [".zip", ".rar", ".7z", ".tar", ".gz"],
            "音频": [".mp3", ".wav", ".flac", ".aac", ".m4a"],
        },
    }


def load_config() -> dict:
    """读取配置文件，不存在则创建默认配置并返回。"""
    config_path = get_config_path()
    if not config_path.exists():
        cfg = get_default_config()
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
            print(f"[配置] 已创建默认配置文件: {config_path}")
        except OSError as e:
            print(f"[配置] 无法创建配置文件 {config_path}: {e}")
            return get_default_config()
        return cfg

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg: dict = json.load(f)
        # 合并默认值，保证新字段不缺
        default = get_default_config()
        for key in default:
            cfg.setdefault(key, default[key])
        return cfg
    except (json.JSONDecodeError, OSError) as e:
        print(f"[配置] 配置文件解析失败，使用默认配置: {e}")
        return get_default_config()


# ── 日志 ──────────────────────────────────────────────────────────────


def setup_logger(config: dict) -> logging.Logger:
    """按配置设置日志器。返回 logger 实例。"""
    logger = logging.getLogger("DesktopOrganizer")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # 避免重复 handler

    # 格式化器
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台 handler (始终输出)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # 文件 handler (按配置)
    if config.get("enable_logging", True):
        log_dir = Path(os.path.expanduser(config.get("log_directory", DEFAULT_LOG_DIR)))
        log_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        log_file = log_dir / f"organize_{today}.log"
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


# ── 文件整理核心 ──────────────────────────────────────────────────────


def should_skip(filepath: Path) -> tuple[bool, str]:
    """
    判断文件是否应跳过。返回 (skip, reason)。
    - 符号链接跳过
    - 隐藏文件（. 开头）跳过
    - 系统文件跳过
    - 非普通文件跳过（目录等）
    """
    filename = filepath.name

    if filepath.is_symlink():
        return True, "符号链接，跳过"
    if filename.startswith("."):
        return True, "隐藏文件，跳过"
    if filename in SYSTEM_FILES:
        return True, "系统文件，跳过"
    if not filepath.is_file():
        return True, "不是普通文件，跳过"
    return False, ""


def get_category(rules: dict, ext: str) -> str | None:
    """
    返回扩展名对应的分类（文件夹名）。
    如果扩展名无匹配，返回 None（归类到"其他文件"）。
    """
    ext_lower = ext.lower()
    for category, exts in rules.items():
        if ext_lower in exts:
            return category
    return None


def organize_folder(folder_path: Path, config: dict, logger: logging.Logger) -> dict:
    """
    整理单个文件夹。返回统计信息 dict。
    """
    stats: dict = {"moved": 0, "skipped": 0, "errors": 0}
    rules: dict = config.get("rules", {})

    if not folder_path.is_dir():
        logger.warning("路径不存在或不是目录，跳过: %s", folder_path)
        stats["errors"] += 1
        return stats

    logger.info("开始整理文件夹: %s", folder_path)

    # 获取文件夹内的条目，按修改时间排序（稳定的排序）
    try:
        entries = sorted(
            folder_path.iterdir(),
            key=lambda p: (p.stat().st_mtime, p.name),
        )
    except PermissionError as e:
        logger.error("权限不足，无法列出目录 %s: %s", folder_path, e)
        stats["errors"] += 1
        return stats

    for entry in entries:
        # ── 跳过判断 ──
        skip, reason = should_skip(entry)
        if skip:
            logger.info("跳过: %s （%s）", entry.name, reason)
            stats["skipped"] += 1
            continue

        # ── 分类 ──
        ext = entry.suffix  # 包含「.」
        category = get_category(rules, ext)
        if category is None:
            category = "其他文件"

        # ── 创建目标子文件夹 ──
        target_dir = folder_path / category
        try:
            target_dir.mkdir(exist_ok=True)
        except OSError as e:
            logger.error("无法创建文件夹 %s: %s", target_dir, e)
            stats["errors"] += 1
            continue

        # ── 防冲突：目标已存在同名文件时添加后缀 ──
        dest = target_dir / entry.name
        if dest.exists():
            stem = entry.stem
            i = 1
            while dest.exists():
                dest = target_dir / f"{stem}_{i}{ext}"
                i += 1

        # ── 移动文件（安全尝试） ──
        try:
            shutil.move(str(entry), str(dest))
            logger.info("移动: %s → %s/", entry.name, category)
            stats["moved"] += 1
        except OSError as e:
            logger.error("移动失败: %s → %s （%s）", entry.name, category, e)
            stats["errors"] += 1

    return stats


def run_once(config: dict, logger: logging.Logger | None = None) -> int:
    """
    执行一次完整整理。返回值：0 成功，1 部分失败。
    """
    if logger is None:
        logger = setup_logger(config)

    logger.info("=" * 50)
    logger.info("整理任务开始")
    logger.info("=" * 50)

    folders: list[str] = config.get("folders", ["~/Desktop"])
    total_stats = {"moved": 0, "skipped": 0, "errors": 0}

    for folder_raw in folders:
        folder_path = Path(os.path.expanduser(folder_raw))
        stats = organize_folder(folder_path, config, logger)
        for k in total_stats:
            total_stats[k] += stats[k]

    logger.info("-" * 30)
    logger.info(
        "整理完成: 移动 %d / 跳过 %d / 错误 %d",
        total_stats["moved"],
        total_stats["skipped"],
        total_stats["errors"],
    )
    logger.info("=" * 50)

    return 0 if total_stats["errors"] == 0 else 1


# ── launchd plist 管理 ──────────────────────────────────────────────


def get_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{SCRIPT_NAME}.plist"


def get_python_exe() -> str:
    """返回当前 Python 解释器路径（确保 launchd 能找到它）。"""
    return sys.executable


def get_script_path() -> Path:
    """返回 organizer.py 的绝对路径。"""
    return get_script_dir() / "organizer.py"


def generate_plist(config: dict) -> dict:
    """生成 plist 字典（plistlib 可直接 dump）。"""
    schedule_time: str = config.get("schedule_time", "03:00")
    try:
        hour, minute = map(int, schedule_time.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 3, 0

    python_exe = get_python_exe()
    script_path = str(get_script_path())

    plist = {
        "Label": SCRIPT_NAME,
        "ProgramArguments": [python_exe, script_path, "--run"],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(
            Path.home() / "Library" / "Logs" / f"{SCRIPT_NAME}.stdout.log"
        ),
        "StandardErrorPath": str(
            Path.home() / "Library" / "Logs" / f"{SCRIPT_NAME}.stderr.log"
        ),
        "RunAtLoad": False,  # 安装时不立即执行
        "KeepAlive": False,  # 执行完即退出
        "ProcessType": "Background",
        "Nice": 1,           # 较低优先级，不影响前台
    }
    return plist


def install_launchd(config: dict) -> bool:
    """生成并加载 plist，启用定时任务。成功返回 True。"""
    plist_path = get_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    plist = generate_plist(config)

    try:
        with open(plist_path, "wb") as f:
            plistlib.dump(plist, f)
        print(f"[launchd] plist 已写入: {plist_path}")
    except OSError as e:
        print(f"[launchd] 写入 plist 失败: {e}")
        return False

    # 加载/重启任务
    cmds = [
        ["launchctl", "unload", str(plist_path)],
        ["launchctl", "load", str(plist_path)],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            # unload 失败可能是因为任务尚未加载 — 非致命
            if cmd[1] == "unload":
                continue
            print(f"[launchd] 加载任务失败: {result.stderr.strip()}")
            return False

    print(f"[launchd] 定时任务已安装，每天 {config.get('schedule_time', '03:00')} 执行")
    print(f"[launchd] 标准输出日志: {plist.get('StandardOutPath', 'N/A')}")
    print(f"[launchd] 错误日志: {plist.get('StandardErrorPath', 'N/A')}")
    return True


def uninstall_launchd() -> bool:
    """卸载 launchd 定时任务并删除 plist 文件。"""
    plist_path = get_plist_path()

    if not plist_path.exists():
        print("[launchd] plist 文件不存在，任务可能已被卸载")
        return True

    # 卸载
    result = subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        msg = result.stderr.strip()
        if "Could not find specified service" not in msg:
            print(f"[launchd] 卸载警告: {msg}")

    # 删除 plist
    try:
        plist_path.unlink()
        print(f"[launchd] 已删除 plist: {plist_path}")
    except OSError as e:
        print(f"[launchd] 删除 plist 失败: {e}")
        return False

    print("[launchd] 定时任务已卸载")
    return True


def status_launchd() -> None:
    """检查 launchd 定时任务状态并打印。"""
    plist_path = get_plist_path()

    # 检查 plist 文件是否存在
    if plist_path.exists():
        print(f"[launchd] plist 文件: 存在 ({plist_path})")
        try:
            with open(plist_path, "rb") as f:
                plist = plistlib.load(f)
            hour = plist.get("StartCalendarInterval", {}).get("Hour", "?")
            minute = plist.get("StartCalendarInterval", {}).get("Minute", "?")
            print(f"[launchd] 计划时间: {hour:02d}:{minute:02d}")
        except Exception:
            pass
    else:
        print("[launchd] plist 文件: 不存在")

    # 检查任务是否已加载
    result = subprocess.run(
        ["launchctl", "list", SCRIPT_NAME],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        print("[launchd] 任务状态: 已加载")
        # 解析输出，格式: "PID\tStatus\tLabel"
        parts = result.stdout.strip().split("\t")
        if len(parts) >= 2:
            pid = parts[0]
            status_code = parts[1]
            print(f"[launchd] PID: {pid if pid != '-' else '未运行'}")
            if status_code != "0" and status_code != "-":
                print(f"[launchd] 最后退出码: {status_code}")
    else:
        print("[launchd] 任务状态: 未加载")


# ── show-config ──────────────────────────────────────────────────────


def show_config(config: dict) -> None:
    """以 YAML-like 格式打印当前配置。"""
    print("当前配置:")
    print(f"  整理文件夹:")
    for f in config.get("folders", []):
        print(f"    - {f}")
    print(f"  定时时间: {config.get('schedule_time', '03:00')}")
    print(f"  日志目录: {config.get('log_directory', DEFAULT_LOG_DIR)}")
    print(f"  日志开关: {'开启' if config.get('enable_logging', True) else '关闭'}")
    print("  分类规则:")
    for cat, exts in config.get("rules", {}).items():
        print(f"    {cat}: {', '.join(exts)}")
    print()
    print("配置文件路径:", get_config_path())


# ── crontab 提示 ─────────────────────────────────────────────────────


def print_crontab_hint(config: dict) -> None:
    """打印 crontab 设置说明（备选方案）。"""
    schedule_time: str = config.get("schedule_time", "03:00")
    try:
        hour, minute = map(int, schedule_time.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 3, 0

    python_exe = get_python_exe()
    script_path = get_script_path()
    log_path = Path.home() / "Library" / "Logs" / f"{SCRIPT_NAME}.cron.log"

    print("=" * 50)
    print("crontab 备选方案（方式 B）")
    print("=" * 50)
    print()
    print(f"在终端运行 crontab -e 添加以下条目:")
    print()
    print(f"  {minute} {hour} * * * {python_exe} {script_path} --run >> {log_path} 2>&1")
    print()
    print(f"保存后即生效。每天 {schedule_time} 执行。")
    print(f"查看当前 crontab: crontab -l")
    print(f"移除所有定时任务: crontab -r")
    print(f"移除该条: crontab -e 然后删除对应行")
    print()


# ── CLI ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="macOS 桌面 & 指定文件夹自动整理工具",
        epilog="不传参数时默认执行 --run",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="立即执行一次文件整理",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="安装 launchd 定时任务",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="卸载 launchd 定时任务",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="查看 launchd 定时任务状态",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="显示当前配置",
    )
    parser.add_argument(
        "--crontab",
        action="store_true",
        help="显示 crontab 设置说明（备选方案）",
    )

    args = parser.parse_args()

    # 加载配置
    config = load_config()

    # 确定动作：无参数 / 只有 --run 都执行整理
    no_args = all(not v for v in vars(args).values())
    if args.run or no_args:
        logger = setup_logger(config)
        exit_code = run_once(config, logger)
        sys.exit(exit_code)

    if args.install:
        success = install_launchd(config)
        print()  # 空行后打印 crontab 备选提示
        print_crontab_hint(config)
        sys.exit(0 if success else 1)

    if args.uninstall:
        success = uninstall_launchd()
        sys.exit(0 if success else 1)

    if args.status:
        status_launchd()
        sys.exit(0)

    if args.show_config:
        show_config(config)
        sys.exit(0)

    if args.crontab:
        print_crontab_hint(config)
        sys.exit(0)


if __name__ == "__main__":
    main()
