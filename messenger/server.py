"""Программа-сервер"""
import argparse
import configparser
import os
import socket
import sys
import json
import time
import select
import logging
import threading

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox

from decorators import log
from log.config import server_log_config
from errors import IncorrectDataRecivedError
from common.variables import *
from common.utils import get_message, send_message
from descriptors import Host, Port
from metaclasses import ServerMeta
from server_gui import HistoryWindow, ConfigWindow, create_stat_model, gui_create_model, MainWindow
from server_database import ServerStorage

# Инициализация логирования сервера.
SERVER_LOGGER = logging.getLogger('server')

# Флаг, что был подключён новый пользователь, нужен чтобы не мучить BD
# постоянными запросами на обновление
new_connection = False
connection_locker = threading.Lock()


@log
def create_arg_parser(default_port, default_address):
    """Парсер аргументов командной строки"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', default=default_port, type=int, nargs='?')
    parser.add_argument('-a', default=default_address, nargs='?')
    namespace = parser.parse_args(sys.argv[1:])
    listen_address = namespace.a
    listen_port = namespace.p

    return listen_address, listen_port


class Server(threading.Thread, metaclass=ServerMeta):
    port = Port()
    # addr = Host()

    def __init__(self, listen_address, listen_port, database):
        # Конструктор предка
        super().__init__()

        # Параметры подключения
        self.addr = listen_address
        self.port = listen_port

        # База данных сервера
        self.database = database

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

    # Обработчик сообщений от клиентов, принимает словарь - сообщение от клиента, проверяет корректность, отправляет
    # словарь-ответ в случае необходимости.
    def handle(self, message, client):
        global new_connection
        SERVER_LOGGER.debug(f'Разбор сообщения от клиента : {message}')

        # Если это сообщение о присутствии, принимаем и отвечаем
        if ACTION in message and message[ACTION] == PRESENCE and TIME in message \
                and USER in message:
            # Если такой пользователь ещё не зарегистрирован, регистрируем,
            # иначе отправляем ответ и завершаем соединение.
            if message[USER][ACCOUNT_NAME] not in self.names.keys():
                self.names[message[USER][ACCOUNT_NAME]] = client
                client_ip, client_port = client.getpeername()
                # Добавление в базу записи входа (таблица активных пользователей)
                self.database.user_login(message[USER][ACCOUNT_NAME], client_ip, client_port)
                send_message(client, {RESPONSE: 200})
                with connection_locker:  # add_new
                    new_connection = True

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
            self.database.process_message(
                message[SENDER], message[TARGET])
            return

        # Если клиент вышел
        elif ACTION in message and message[ACTION] == EXIT and ACCOUNT_NAME in message \
                and self.names[message[ACCOUNT_NAME]] == client:
            # Удаление из базы (таблица активных пользователей) вышедшего пользователя
            self.database.user_logout(message[ACCOUNT_NAME])
            self.clients.remove(self.names[message[ACCOUNT_NAME]])
            self.names[message[ACCOUNT_NAME]].close()
            del self.names[message[ACCOUNT_NAME]]
            with connection_locker:  # add_new
                new_connection = True
            return

        # Если это запрос контакт-листа
        elif ACTION in message and message[ACTION] == GET_CONTACTS and USER in message and \
                self.names[message[USER]] == client:
            response = RESPONSE_202
            response[LIST_INFO] = self.database.get_contacts(message[USER])
            send_message(client, response)  # add_new

        # Если это добавление контакта
        elif ACTION in message and message[ACTION] == ADD_CONTACT and ACCOUNT_NAME in message and USER in message \
                and self.names[message[USER]] == client:
            self.database.add_contact(message[USER], message[ACCOUNT_NAME])
            send_message(client, RESPONSE_200)  # add_new

        # Если это удаление контакта
        elif ACTION in message and message[ACTION] == REMOVE_CONTACT and ACCOUNT_NAME in message and USER in message \
                and self.names[message[USER]] == client:
            self.database.remove_contact(message[USER], message[ACCOUNT_NAME])
            send_message(client, RESPONSE_200)  # add_new

        # Если это запрос известных пользователей
        elif ACTION in message and message[ACTION] == USERS_REQUEST and ACCOUNT_NAME in message \
                and self.names[message[ACCOUNT_NAME]] == client:
            response = RESPONSE_202
            response[LIST_INFO] = [user[0]
                                   for user in self.database.users_list()]
            send_message(client, response)  # add_new

        # Иначе отдаём Bad request
        else:
            response = {RESPONSE: 400, ERROR: 'Некорректный запрос'}
            send_message(client, response)
            return

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

    def run(self):
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
            except OSError as err:
                SERVER_LOGGER.error(f'Ошибка работы с сокетами: {err}')

            # принимаем сообщения и, если ошибка, исключаем клиента.
            if recv_data_lst:
                for client_with_message in recv_data_lst:
                    try:
                        self.handle(get_message(client_with_message), client_with_message)
                    except (OSError):
                        # Ищем клиента в словаре клиентов и удаляем его из него
                        # и базы подключённых
                        SERVER_LOGGER.info(
                            f'Клиент {client_with_message.getpeername()} отключился от сервера.')
                        for name in self.names:  # add_new
                            if self.names[name] == client_with_message:
                                self.database.user_logout(name)
                                del self.names[name]
                                break
                        self.clients.remove(client_with_message)

            # Если есть сообщения для отправки и ожидающие клиенты, отправляем им сообщение.
            for mess in self.messages:
                try:
                    self.process_message(mess, send_data_lst)
                except (ConnectionAbortedError, ConnectionError, ConnectionResetError, ConnectionRefusedError):
                    SERVER_LOGGER.info(f'Связь с клиентом с именем {mess[TARGET]} была потеряна')
                    self.clients.remove(self.names[mess[TARGET]])
                    self.database.user_logout(mess[TARGET])  # add_new
                    del self.names[mess[TARGET]]
            self.messages.clear()


def print_help():
    print('Поддерживаемые команды:')
    print('users - список известных пользователей')
    print('conn - список подключенных пользователей')
    print('history - история входов пользователя')
    print('exit - завершение работы сервера.')
    print('help - вывод справки по поддерживаемым командам')


def main():
    # Загрузка файла конфигурации сервера
    config = configparser.ConfigParser()

    dir_path = os.path.dirname(os.path.realpath(__file__))
    config.read(f"{dir_path}/{'server.ini'}")

    # Загрузка параметров командной строки, если нет параметров, то задаём значения по умоланию.
    listen_address, listen_port = create_arg_parser(
        config['SETTINGS']['Default_port'], config['SETTINGS']['Listen_Address'])

    # Инициализация базы данных
    database = ServerStorage(os.path.join(
            config['SETTINGS']['Database_path'],
            config['SETTINGS']['Database_file']))

    # Создание экземпляра класса - сервера и его запуск:
    server = Server(listen_address, listen_port, database)
    server.daemon = True
    server.start()  # Запуск в отдельном потоке(помним что start) #threding

    # Создаём графическое окуружение для сервера:
    server_app = QApplication(sys.argv)  # создаем приложение
    main_window = MainWindow()
    # ЗАПУСК РАБОТАЕТ ПАРАЛЕЛЬНО СЕРВЕРА(К ОКНУ)
    # ГЛАВНОМ ПОТОКЕ ЗАПУСКАЕМ НАШ GUI - ГРАФИЧЕСКИЙ ИНТЕРФЕС ПОЛЬЗОВАТЕЛЯ

    # Инициализируем параметры в окна Главное окно
    main_window.statusBar().showMessage('Server Working')  # подвал
    main_window.active_clients_table.setModel(
        gui_create_model(database))  # заполняем таблицу основного окна делаем разметку и заполняем ее
    main_window.active_clients_table.resizeColumnsToContents()
    main_window.active_clients_table.resizeRowsToContents()

    # Функция обновляющая список подключённых, проверяет флаг подключения, и
    # если надо обновляет список
    def list_update():
        global new_connection
        if new_connection:
            main_window.active_clients_table.setModel(
                gui_create_model(database))
            main_window.active_clients_table.resizeColumnsToContents()
            main_window.active_clients_table.resizeRowsToContents()
            with connection_locker:
                new_connection = False

    # Функция создающяя окно со статистикой клиентов
    def show_statistics():
        global stat_window
        stat_window = HistoryWindow()
        stat_window.history_table.setModel(create_stat_model(database))
        stat_window.history_table.resizeColumnsToContents()
        stat_window.history_table.resizeRowsToContents()
        # stat_window.show()

    # Функция создающяя окно с настройками сервера.
    def server_config():
        global config_window
        # Создаём окно и заносим в него текущие параметры
        config_window = ConfigWindow()
        config_window.db_path.insert(config['SETTINGS']['Database_path'])
        config_window.db_file.insert(config['SETTINGS']['Database_file'])
        config_window.port.insert(config['SETTINGS']['Default_port'])
        config_window.ip.insert(config['SETTINGS']['Listen_Address'])
        config_window.save_btn.clicked.connect(save_server_config)

    # Функция сохранения настроек
    def save_server_config():
        global config_window
        message = QMessageBox()
        config['SETTINGS']['Database_path'] = config_window.db_path.text()
        config['SETTINGS']['Database_file'] = config_window.db_file.text()
        try:
            port = int(config_window.port.text())
        except ValueError:
            message.warning(config_window, 'Ошибка', 'Порт должен быть числом')
        else:
            config['SETTINGS']['Listen_Address'] = config_window.ip.text()
            if 1023 < port < 65536:
                config['SETTINGS']['Default_port'] = str(port)
                print(port)
                with open('server.ini', 'w') as conf:
                    config.write(conf)
                    message.information(
                        config_window, 'OK', 'Настройки успешно сохранены!')
            else:
                message.warning(
                    config_window,
                    'Ошибка',
                    'Порт должен быть от 1024 до 65536')

    # Таймер, обновляющий список клиентов 1 раз в секунду
    timer = QTimer()
    timer.timeout.connect(list_update)
    timer.start(1000)

    # Связываем кнопки с процедурами
    main_window.refresh_button.triggered.connect(list_update)
    main_window.show_history_button.triggered.connect(show_statistics)
    main_window.config_btn.triggered.connect(server_config)

    # Запускаем GUI
    server_app.exec_()


if __name__ == "__main__":
    main()
