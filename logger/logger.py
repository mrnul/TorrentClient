import logging


class Logger:
    def __init__(self, fmt: str = '%(asctime)s %(levelname)s %(message)s'):
        self.formatter = logging.Formatter(fmt)

    def get(self, log_file: str, name: str, level: str = 'INFO') -> logging.Logger:
        logger = logging.getLogger(name)
        handler = logging.FileHandler(log_file)
        handler.setFormatter(self.formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        return logger
