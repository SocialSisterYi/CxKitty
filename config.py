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
SESSIONPATH = Path(conf.get("sessionPath", "session"))
LOGPATH = Path(conf.get("logPath", "logs"))

# 基本配置
MULTI_SESS: bool = conf.get("multiSession", True)
TUI_MAX_HEIGHT: int = conf.get("tUIMaxHeight", 25)
MASKACC: bool = conf.get("maskAcc", True)

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
