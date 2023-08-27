import logging


def makeSimpleLogger(name, level=logging.INFO):
    # TODO use extra ...
    logger = logging.getLogger(name)
    if logger.handlers:  # prevent multiple handlers
        return logger

    logger.setLevel(level)
    ch = logging.StreamHandler()  # FileHander goes to disk
    fmt = ('[%(asctime)s] - %(levelname)8s - '
           '%(name)14s - '
           '%(filename)16s:%(lineno)-4d - '
           '%(message)s')
    formatter = logging.Formatter(fmt)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


log = makeSimpleLogger('hyputils')
logd = log.getChild('data')
