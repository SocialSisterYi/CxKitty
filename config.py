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
SESSIONS_PATH = Path(conf.get("session_path", "session"))
LOGS_PATH = Path(conf.get("log_path", "logs"))
EXPORT_PATH = Path(conf.get("export_path"))
FACE_PATH = Path(conf.get("face_image_path"))

# 创建导出目录
if not EXPORT_PATH.exists():
    EXPORT_PATH.mkdir(parents=True)

# 基本配置
MULTI_SESS: bool = conf.get("multi_session", True)
TUI_MAX_HEIGHT: int = conf.get("tui_max_height", 25)
MASKACC: bool = conf.get("mask_acc", True)
FETCH_UPLOADED_FACE: bool = conf.get("fetch_uploaded_face", True)

# 任务配置
WORK: dict = conf.get("work", {})
VIDEO: dict = conf.get("video", {})
DOCUMENT: dict = conf.get("document", {})
EXAM: dict = conf.get("exam", {})

# 任务使能配置
WORK_EN: bool = WORK.get("enable", True)
VIDEO_EN: bool = VIDEO.get("enable", True)
DOCUMENT_EN: bool = DOCUMENT.get("enable", True)

# 任务延时配置
WORK_WAIT: int = WORK.get("wait", 15)
VIDEO_WAIT: int = VIDEO.get("wait", 15)
DOCUMENT_WAIT: int = DOCUMENT.get("wait", 15)

# 搜索器配置
SEARCHERS: list = conf.get("searchers", [])
