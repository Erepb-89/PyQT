"""Утилиты"""

import json
import sys
from .variables import MAX_PACKAGE_LENGTH, ENCODING
sys.path.append('../')
from decorators import log
from errors import NonDictInputError, IncorrectDataRecivedError


@log
def get_message(client):
    """
    Утилита приёма и декодирования сообщения
    принимает байты выдаёт словарь, если принято что-то другое - отдаёт ошибку значения
    :param client:
    :return:
    """

    encoded_response = client.recv(MAX_PACKAGE_LENGTH)
    if isinstance(encoded_response, bytes):
        json_response = encoded_response.decode(ENCODING)
        response = json.loads(json_response)
        if isinstance(response, dict):
            return response
        raise IncorrectDataRecivedError
    raise IncorrectDataRecivedError


@log
def send_message(sock, message):
    """
    Утилита кодирования и отправки сообщения
    принимает словарь и отправляет его
    :param sock:
    :param message:
    :return:
    """
    if not isinstance(message, dict):
        raise NonDictInputError
    js_message = json.dumps(message)
    encoded_message = js_message.encode(ENCODING)
    sock.send(encoded_message)
