import logging


class Logger:
    def __init__(self, name: str, file: str, level: str | int):
        self.logger = logging.getLogger(name)
        formatter = logging.Formatter('%(asctime)s - %(funcName)s %(levelname)s : %(message)s')
        file_handler = logging.FileHandler(file, mode='w')
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        self.logger.setLevel(level)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(stream_handler)

    def get(self) -> logging.Logger:
        return self.logger
