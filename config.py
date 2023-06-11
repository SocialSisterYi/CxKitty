import warnings
from pathlib import Path

import yaml

try:
    with open("config.yml", "r", encoding="utf8") as fp:
        conf: dict = yaml.load(fp, yaml.FullLoader)
except FileNotFoundError:
    conf = {}
    warnings.warn("Config file not found", RuntimeWarning)

# 路径配置
SESSIONPATH = Path(conf.get("session_path", "session"))
LOGPATH = Path(conf.get("log_path", "logs"))

# 基本配置
MULTI_SESS: bool = conf.get("multi_session", True)
TUI_MAX_HEIGHT: int = conf.get("tui_max_height", 25)
MASKACC: bool = conf.get("mask_acc", True)

# 任务配置
EXAM: dict = conf.get("exam", {})
VIDEO: dict = conf.get("video", {})
DOCUMENT: dict = conf.get("document", {})

# 任务使能配置
EXAM_EN: bool = EXAM.get("enable", True)
VIDEO_EN: bool = VIDEO.get("enable", True)
DOCUMENT_EN: bool = DOCUMENT.get("enable", True)

# 任务延时配置
EXAM_WAIT: int = EXAM.get("wait", 15)
VIDEO_WAIT: int = VIDEO.get("wait", 15)
DOCUMENT_WAIT: int = DOCUMENT.get("wait", 15)

# 搜索器配置
SEARCHERS: list = conf.get("searchers", [])
