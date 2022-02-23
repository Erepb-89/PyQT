"""Константы"""
import logging

# Порт по умолчанию для сетевого ваимодействия
DEFAULT_PORT = 7777
# IP адрес по умолчанию для подключения клиента
DEFAULT_IP_ADDRESS = '127.0.0.1'
# Максимальная очередь подключений
MAX_CONNECTIONS = 5
# Максимальная длина сообщения в байтах
MAX_PACKAGE_LENGTH = 640
# Кодировка проекта
ENCODING = 'utf-8'

# Прококол JIM основные ключи:
ACTION = 'action'
TIME = 'time'
TYPE = 'type'
USER = 'user'
ACCOUNT_NAME = 'account_name'
SENDER = 'sender'

# Прочие ключи, используемые в протоколе
AUTHENTICATE = 'authenticate'
PRESENCE = 'presence'
RESPONSE = 'response'
ALERT = 'alert'
ERROR = 'error'
STATUS = 'status'
PASSWORD = 'password'
PROBE = 'probe'
PORT = '-p'
IP_ADDRESS = '-a'
MESSAGE = 'message'
MESSAGE_TEXT = 'mess_text'
EXIT = 'exit'
TARGET = 'to'

# responses
RESPONSE_200 = "Необязательное сообщение/уведомление"
RESPONSE_402 = 'This could be "wrong password" or "no account with that name"'
RESPONSE_409 = "Someone is already connected with the given user name"

# logging
FORMATTER = logging.Formatter("%(asctime)s - %(levelname)s - %(filename)s - %(message)s")
LOGGING_LEVEL = logging.DEBUG
