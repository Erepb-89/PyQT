"""Декораторы"""

import sys
import logging
import log.config.server_log_config
import log.config.client_log_config

print(sys.argv[0].split('/')[-1])
if sys.argv[0].split('/')[-1].find('client') == -1:
    LOGGER = logging.getLogger('server')
else:
    LOGGER = logging.getLogger('client')


def log(func):
    """Функция-Декоратор"""

    def save_logger(*args, **kwargs):
        """Обертка"""
        LOGGER.debug(f'Была вызвана функция {func.__name__} c параметрами {args} , {kwargs}. Вызов из модуля {func.__module__}')
        res = func(*args, **kwargs)
        return res

    return save_logger
