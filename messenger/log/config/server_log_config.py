import sys
import os
import logging
import logging.handlers

sys.path.append('../../')
from common.variables import LOGGING_LEVEL, FORMATTER

# Создаем логгер - регистратор верхнего уроовня с именем client
SERVER_LOG = logging.getLogger('server')
# Установить уровень важности

PATH = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(os.path.split(PATH)[0], 'logs/server.log')

# Создаем обработчик, который выводит сообщения в поток stderr
STREAM_HANDLER = logging.StreamHandler(sys.stderr)
STREAM_HANDLER.setLevel(logging.ERROR)

# Создать обработчик, который выводит сообщения в файл
FILE_HANDLER = logging.handlers.TimedRotatingFileHandler(PATH, encoding='utf8', interval=1, when='D')

# подключаем объект Formatter к обработчикам
STREAM_HANDLER.setFormatter(FORMATTER)
FILE_HANDLER.setFormatter(FORMATTER)

# Добавляем обработчики к регистратору
SERVER_LOG.addHandler(STREAM_HANDLER)
SERVER_LOG.addHandler(FILE_HANDLER)
SERVER_LOG.setLevel(LOGGING_LEVEL)

# Отладка
if __name__ == '__main__':
    SERVER_LOG.critical('Критическая ошибка')
    SERVER_LOG.error('Ошибка')
    SERVER_LOG.warning('Предупреждение!')
    SERVER_LOG.debug('Отладочная информация')
    SERVER_LOG.info('Замечательный день для релиза!')
