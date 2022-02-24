"""Программа-сервер"""
import argparse
import socket
import sys
import json
import time
import select
import logging
from decorators import log
from log.config import server_log_config
from errors import IncorrectDataRecivedError
from common.variables import ACTION, ACCOUNT_NAME, RESPONSE, MAX_CONNECTIONS, \
    PRESENCE, TIME, USER, ERROR, DEFAULT_PORT, MESSAGE, MESSAGE_TEXT, SENDER, EXIT, TARGET
from common.utils import get_message, send_message
from messenger.descriptors import Host, Port
from messenger.metaclasses import ServerMeta

# Инициализация логирования сервера.
SERVER_LOGGER = logging.getLogger('server')


@log
def create_arg_parser():
    """Парсер аргументов коммандной строки"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', default=DEFAULT_PORT, type=int, nargs='?')
    parser.add_argument('-a', default='0.0.0.0', nargs='?')
    namespace = parser.parse_args(sys.argv[1:])
    listen_address = namespace.a
    listen_port = namespace.p

    return listen_address, listen_port


class Server(metaclass=ServerMeta):
    port = Port()
    addr = Host()

    def __init__(self, listen_address, listen_port):
        # Параметры подключения
        self.addr = listen_address
        self.port = listen_port

        # Список подключённых клиентов.
        self.clients = []

        # Список сообщений на отправку.
        self.messages = []

        # Словарь содержащий сопоставленные имена и соответствующие им сокеты.
        self.names = dict()

    def init_socket(self):
        SERVER_LOGGER.info(f'Запущен сервер, порт для подключений: {self.port}, '
                           f'адрес с которого принимаются подключения: {self.addr}')
        # Готовим сокет
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((self.addr, self.port))
        sock.settimeout(0.5)

        # Начинаем слушать сокет.
        self.sock = sock
        self.sock.listen()

    # @log
    # Обработчик сообщений от клиентов, принимает словарь - сообщение от клиента, проверяет корректность, отправляет
    # словарь-ответ в случае необходимости.
    def handle(self, message, client):
        SERVER_LOGGER.debug(f'Разбор сообщения от клиента : {message}')
        # Если это сообщение о присутствии, принимаем и отвечаем
        if ACTION in message and message[ACTION] == PRESENCE and TIME in message \
                and USER in message:
            # Если это новый пользователь, регистрируем
            if message[USER][ACCOUNT_NAME] not in self.names.keys():
                self.names[message[USER][ACCOUNT_NAME]] = client
                send_message(client, {RESPONSE: 200})
            # Иначе отправляем ошибку и закрываем соединение
            else:
                response = {RESPONSE: 400, ERROR: 'Имя пользователя уже занято'}
                send_message(client, response)
                self.clients.remove(client)
                client.close()
            return
        # Если это сообщение, то добавляем его в очередь сообщений. Ответ не требуется.
        elif ACTION in message and message[ACTION] == MESSAGE and \
                TARGET in message and TIME in message and MESSAGE_TEXT in message:
            self.messages.append(message)
            return
        # Если клиент вышел
        elif ACTION in message and message[ACTION] == EXIT and ACCOUNT_NAME in message:
            self.clients.remove(self.names[message[ACCOUNT_NAME]])
            self.names[message[ACCOUNT_NAME]].close()
            del self.names[message[ACCOUNT_NAME]]
            return
        # Иначе отдаём Bad request
        else:
            response = {RESPONSE: 400, ERROR: 'Некорректный запрос'}
            send_message(client, response)
            return

    # @log
    # Функция адресной отправки сообщения определённому клиенту. Принимает словарь сообщение, список зарегистрированых
    # пользователей и слушающие сокеты. Ничего не возвращает.
    def process_message(self, message, listen_socks):
        if message[TARGET] in self.names and self.names[message[TARGET]] in listen_socks:
            send_message(self.names[message[TARGET]], message)
            SERVER_LOGGER.info(
                f'Отправлено сообщение пользователю {message[TARGET]} от пользователя {message[SENDER]}.')
        elif message[TARGET] in self.names and self.names[message[TARGET]] not in listen_socks:
            raise ConnectionError
        else:
            SERVER_LOGGER.error(
                f'Пользователь {message[TARGET]} не зарегистрирован на сервере, отправка сообщения невозможна.')

    def main_loop(self):
        # Инициализация Сокета
        self.init_socket()

        # Основной цикл программы сервера
        while True:
            # Ждём подключения, если таймаут вышел, ловим исключение.
            try:
                client, client_address = self.sock.accept()
            except OSError:
                pass
            else:
                SERVER_LOGGER.info(f'Установлено соединение с ПК {client_address}')
                self.clients.append(client)

            recv_data_lst = []
            send_data_lst = []
            err_lst = []
            # Проверяем на наличие ждущих клиентов
            try:
                if self.clients:
                    recv_data_lst, send_data_lst, err_lst = select.select(self.clients, self.clients, [], 0)
            except OSError:
                pass

            # принимаем сообщения и если там есть сообщения,
            # кладём в словарь, если ошибка, исключаем клиента.
            if recv_data_lst:
                for client_with_message in recv_data_lst:
                    try:
                        self.handle(get_message(client_with_message), client_with_message)
                    except:
                        SERVER_LOGGER.info(f'Клиент {client_with_message.getpeername()} отключился от сервера.')
                        self.clients.remove(client_with_message)

            # Если есть сообщения для отправки и ожидающие клиенты, отправляем им сообщение.
            for mess in self.messages:
                try:
                    self.process_message(mess, send_data_lst)
                except:
                    SERVER_LOGGER.info(f'Связь с клиентом с именем {mess[TARGET]} была потеряна')
                    self.clients.remove(self.names[mess[TARGET]])
                    del self.names[mess[TARGET]]
            self.messages.clear()


def main():
    # Загрузка параметров командной строки, если нет параметров, то задаём значения по умоланию.
    listen_address, listen_port = create_arg_parser()

    # Создание экземпляра класса - сервера.
    server = Server(listen_address, listen_port)
    server.main_loop()


if __name__ == "__main__":
    main()
