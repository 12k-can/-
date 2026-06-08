# macOS 桌面 & 文件夹自动整理工具

一个轻量级的 Python 3 脚本，可自动整理 Mac 桌面和指定文件夹中的文件——根据扩展名分类到对应的子文件夹，并支持通过 `launchd` 或 `crontab` 每天定时执行。

## 功能特点

- **智能分类** — 图片、文档、视频、压缩包、音频自动归类，未匹配的文件归入「其他文件」
- **安全跳过** — 符号链接、隐藏文件、系统文件（`.DS_Store` 等）、被占用文件自动跳过
- **定时执行** — 通过 macOS 原生 `launchd` 或 `crontab` 每天指定时间自动运行
- **可配置** — 通过 `config.json` 自定义整理文件夹、分类规则、定时时间
- **日志记录** — 每次操作写入日期命名的日志文件，便于回溯
- **零依赖** — 仅使用 Python 3 标准库，无需安装任何第三方包

## 项目结构

```
desktop-organizer/
├── organizer.py        # 主程序
├── config.json         # 配置文件（首次运行自动生成默认配置）
├── requirements.txt    # 依赖说明（空：纯标准库）
└── README.md           # 本文件
```

## 系统要求

- macOS 10.15 (Catalina) 及以上
- Python 3.7+（macOS 10.15 自带 Python 3.8+）

## 快速开始

### 1. 下载 / 克隆项目

```bash
cd ~/Desktop            # 或你喜欢的任意目录
# 把本项目所有文件拷贝到 desktop-organizer/ 文件夹
cd desktop-organizer
```

### 2. 运行（无需安装依赖）

```bash
# 直接执行一次整理（使用默认配置：整理桌面）
python organizer.py --run
```

首次运行会自动在脚本同目录生成默认的 `config.json` 配置文件。

### 3. 自定义配置

编辑 `config.json`：

```json
{
    "folders": ["~/Desktop", "~/Downloads"],
    "schedule_time": "03:00",
    "enable_logging": true,
    "log_directory": "~/Library/Logs/DesktopOrganizer",
    "rules": {
        "图片": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".heic", ".tiff"],
        "文档": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv", ".pages", ".numbers", ".key"],
        "视频": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"],
        "压缩包": [".zip", ".rar", ".7z", ".tar", ".gz"],
        "音频": [".mp3", ".wav", ".flac", ".aac", ".m4a"]
    }
}
```

**字段说明：**

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `folders` | 要整理的文件夹路径列表（支持 `~` 开头） | `["~/Desktop"]` |
| `schedule_time` | 定时执行时间，24 小时制 HH:MM | `"03:00"` |
| `enable_logging` | 是否启用文件日志 | `true` |
| `log_directory` | 日志保存目录 | `~/Library/Logs/DesktopOrganizer` |
| `rules` | 分类规则：文件夹名 → 扩展名列表 | 见上表 |

> **提示**：你可以添加自定义分类，比如 `"代码": [".py", ".js", ".ts", ".go", ".rs", ".java"]`。

## 命令用法

```bash
python organizer.py                    # 等同于 --run
python organizer.py --run              # 立即执行一次整理
python organizer.py --install          # 安装 launchd 定时任务
python organizer.py --uninstall        # 卸载 launchd 定时任务
python organizer.py --status           # 查看定时任务状态
python organizer.py --show-config      # 打印当前配置
python organizer.py --crontab          # 显示 crontab 设置说明
```

## 设置定时执行

### 方式 A（推荐）：launchd

使用 macOS 自带的 `launchd` 任务调度系统，安装/卸载均通过脚本完成：

```bash
# 安装定时任务（默认每天 03:00 执行）
python organizer.py --install

# 查看任务状态
python organizer.py --status

# 卸载定时任务
python organizer.py --uninstall
```

安装时脚本会自动：

1. 生成 plist 文件到 `~/Library/LaunchAgents/com.user.dailyorganizer.plist`
2. 通过 `launchctl load` 加载任务
3. 输出日志路径供后续排查

**日志位置：**

- 整理操作日志：`~/Library/Logs/DesktopOrganizer/organize_YYYY-MM-DD.log`
- launchd 标准输出：`~/Library/Logs/com.user.dailyorganizer.stdout.log`
- launchd 错误输出：`~/Library/Logs/com.user.dailyorganizer.stderr.log`

> **提示**：如果修改了 `config.json` 中的定时时间，重新运行 `--install` 即可生效。

### 方式 B（备选）：crontab

```bash
# 查看 crontab 安装说明
python organizer.py --crontab
```

脚本会打印类似下方的 crontab 条目：

```
0 3 * * * /usr/bin/python3 /path/to/desktop-organizer/organizer.py --run >> ~/Library/Logs/com.user.dailyorganizer.cron.log 2>&1
```

**手动操作步骤：**

```bash
crontab -e                        # 编辑 crontab
# 粘贴上述条目，保存退出
crontab -l                        # 确认已生效
```

## 命令示例

整理桌面 + 下载文件夹：

```json
{
    "folders": ["~/Desktop", "~/Downloads"]
}
```

增加代码文件分类：

```json
{
    "rules": {
        "图片": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".heic", ".tiff"],
        "文档": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv", ".pages", ".numbers", ".key"],
        "视频": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"],
        "压缩包": [".zip", ".rar", ".7z", ".tar", ".gz"],
        "音频": [".mp3", ".wav", ".flac", ".aac", ".m4a"],
        "代码": [".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp", ".swift"],
        "图片设计": [".psd", ".ai", ".sketch", ".fig", ".xd"]
    }
}
```

## 日志示例

日志文件保存在 `~/Library/Logs/DesktopOrganizer/organize_2026-06-03.log`：

```
[2026-06-03 03:00:01] INFO: ==================================================
[2026-06-03 03:00:01] INFO: 整理任务开始
[2026-06-03 03:00:01] INFO: ==================================================
[2026-06-03 03:00:01] INFO: 开始整理文件夹: /Users/username/Desktop
[2026-06-03 03:00:01] INFO: 跳过: .DS_Store （系统文件，跳过）
[2026-06-03 03:00:01] INFO: 移动: 会议纪要.pdf → 文档/
[2026-06-03 03:00:01] INFO: 移动: 暑假照片.jpg → 图片/
[2026-06-03 03:00:01] INFO: 移动: 项目演示.mp4 → 视频/
[2026-06-03 03:00:02] INFO: 跳过: 待处理（符号链接，跳过）
[2026-06-03 03:00:02] INFO: ------------------------------
[2026-06-03 03:00:02] INFO: 整理完成: 移动 14 / 跳过 3 / 错误 0
[2026-06-03 03:00:02] INFO: ==================================================
```

## 故障排除

| 问题 | 可能原因 | 解决 |
|------|----------|------|
| `launchctl load` 失败 | plist 路径包含空格 | 路径不要有空格，或修改 `SCRIPT_NAME` |
| 文件未移动 | 权限不足 | 确保对目标文件夹有读写权限 |
| 定时任务未执行 | launchd 未加载 | 运行 `python organizer.py --status` 检查 |
| 找不到 config.json | 工作目录不对 | 配置文件在脚本同目录下 |

## 许可

MIT License
