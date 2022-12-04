import logging

from utils import CONF_LOGPATH


class Logger:
    def __init__(self, name: str, level=logging.DEBUG, fmt=None):
        if not CONF_LOGPATH.is_dir():
            CONF_LOGPATH.mkdir(parents=True)
        self.logger = logging.getLogger(name)
        self.level = level
        self.logger.setLevel(self.level)
        if fmt is None:
            self.fmt = '%(asctime)s [%(name)s] %(levelname)s -> %(message)s'
        else:
            self.fmt = fmt
    
    def set_loginfo(self, phone):
        self.phone = phone
        if not self.logger.handlers:
            fh = logging.FileHandler(f'logs/cxkitty_{self.phone}.log', encoding='utf8')
            fh.setLevel(self.level)
            fh.setFormatter(logging.Formatter(self.fmt))
            self.logger.addHandler(fh)
    
    def debug(self, msg):
        self.logger.debug(msg)
    
    def info(self, msg):
        self.logger.info(msg)
        
    def warning(self, msg):
        self.logger.warning(msg)
        
    def error(self, msg):
        self.logger.error(msg)