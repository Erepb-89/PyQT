"""Программа-клиент"""
import argparse
import sys
import json
import socket
import threading
import time
import logging
from decorators import log
from log.config import client_log_config
from errors import ReqFieldMissingError, ServerError, IncorrectDataRecivedError
from common.variables import *
from common.utils import get_message, send_message
from messenger.metaclasses import ClientMeta
from client_database import ClientDatabase

# Инициализация клиентского логгера
CLIENT_LOGGER = logging.getLogger('client')

# Объект блокировки сокета и работы с базой данных
socket_lock = threading.Lock()
database_lock = threading.Lock()


# Класс формирования и отправки сообщений на сервер и взаимодействия с пользователем.
class ClientSender(threading.Thread, metaclass=ClientMeta):
    def __init__(self, account_name, sock, database):
        self.account_name = account_name
        self.sock = sock
        self.database = database
        super().__init__()

    def create_exit_message(self):
        """Функция создаёт словарь с сообщением о выходе"""
        return {
            ACTION: EXIT,
            TIME: time.time(),
            ACCOUNT_NAME: self.account_name
        }

    def create_message(self):
        """Функция запрашивает текст сообщения и возвращает его.
        Так же завершает работу при вводе подобной команды
        """
        mes_target = input('Введите получателя сообщения: ')
        message = input('Введите сообщение для отправки: ')

        # Проверим, что получатель существует
        with database_lock:
            if not self.database.check_user(mes_target):
                CLIENT_LOGGER.error(f'Попытка отправить сообщение незарегистрированному получателю: {mes_target}')
                return

        message_dict = {
            ACTION: MESSAGE,
            SENDER: self.account_name,
            TARGET: mes_target,
            TIME: time.time(),
            MESSAGE_TEXT: message
        }
        CLIENT_LOGGER.debug(f'Сформирован словарь сообщения: {message_dict}')

        # Сохраняем сообщения для истории
        with database_lock:
            self.database.save_message(self.account_name, mes_target, message)

        # Необходимо дождаться освобождения сокета для отправки сообщения
        with socket_lock:
            try:
                send_message(self.sock, message_dict)
                CLIENT_LOGGER.debug(f'Отправлено сообщение для пользователя {mes_target}')
            except OSError as error:
                if error.errno:
                    CLIENT_LOGGER.critical('Потеряно соединение с сервером.')
                    exit(1)
                else:
                    CLIENT_LOGGER.error('Не удалось передать сообщение. Таймаут соединения')

    def run(self):
        """Функция взаимодействия с пользователем, запрашивает команды, отправляет сообщения"""
        self.print_help()
        while True:
            command = input('Введите команду: ')
            if command == 'message':
                self.create_message()

            elif command == 'help':
                self.print_help()

            elif command == 'exit':
                with socket_lock:
                    try:
                        send_message(self.sock, self.create_exit_message())
                    except:
                        pass
                    print('Завершение соединения.')
                    CLIENT_LOGGER.info('Завершение работы по команде пользователя.')
                # Задержка необходима, чтобы успело уйти сообщение о выходе
                time.sleep(0.5)
                break

            # Список контактов
            elif command == 'contacts':
                with database_lock:
                    contacts_list = self.database.get_contacts()
                for contact in contacts_list:
                    print(contact)

            # Редактирование контактов
            elif command == 'edit':
                self.edit_contacts()

            # история сообщений.
            elif command == 'history':
                self.print_history()
            else:
                print('Команда не распознана, попробуйте снова. help - вывести поддерживаемые команды.')

    def print_help(self):
        """Функция, выводящая справку по использованию"""
        print('Поддерживаемые команды:')
        print('message - отправить сообщение. Кому и текст будет запрошены отдельно.')
        print('history - история сообщений')
        print('contacts - список контактов')
        print('edit - редактирование списка контактов')
        print('help - вывести подсказки по командам')
        print('exit - выход из программы')

    # Функция выводящая историю сообщений
    def print_history(self):
        ask = input('Показать входящие сообщения - in, исходящие - out, все - просто Enter: ')
        with database_lock:
            if ask == 'in':
                history_list = self.database.get_history(to_who=self.account_name)
                for message in history_list:
                    print(f'\nСообщение от пользователя: {message[0]} от {message[3]}:\n{message[2]}')
            elif ask == 'out':
                history_list = self.database.get_history(from_who=self.account_name)
                for message in history_list:
                    print(f'\nСообщение пользователю: {message[1]} от {message[3]}:\n{message[2]}')
            else:
                history_list = self.database.get_history()
                for message in history_list:
                    print(
                        f'\nСообщение от пользователя: {message[0]}, пользователю {message[1]} от {message[3]}\n{message[2]}')

    # Функция изменения контактов
    def edit_contacts(self):
        ans = input('Для удаления введите del, для добавления add: ')
        if ans == 'del':
            edit = input('Введите имя удаляемого контакта: ')
            with database_lock:
                if self.database.check_contact(edit):
                    self.database.del_contact(edit)
                else:
                    CLIENT_LOGGER.error('Попытка удаления несуществующего контакта.')
        elif ans == 'add':
            # Проверка на возможность такого контакта
            edit = input('Введите имя создаваемого контакта: ')
            if self.database.check_user(edit):
                with database_lock:
                    self.database.add_contact(edit)
                with socket_lock:
                    try:
                        add_contact(self.sock, self.account_name, edit)
                    except ServerError:
                        CLIENT_LOGGER.error('Не удалось отправить информацию на сервер.')


# Класс-приёмник сообщений с сервера. Принимает сообщения, выводит в консоль.
class ClientReader(threading.Thread, metaclass=ClientMeta):
    def __init__(self, account_name, sock, database):
        self.account_name = account_name
        self.sock = sock
        self.database = database
        super().__init__()

    # Основной цикл приёмника сообщений, принимает сообщения, выводит в консоль. Завершается при потере соединения.
    def run(self):
        while True:
            # Отдыхаем секунду и снова пробуем захватить сокет.
            # если не сделать тут задержку, то второй поток может достаточно долго ждать освобождения сокета.
            time.sleep(1)
            with socket_lock:
                try:
                    message = get_message(self.sock)

                # Принято некорректное сообщение
                except IncorrectDataRecivedError:
                    CLIENT_LOGGER.error(f'Не удалось декодировать полученное сообщение.')
                # Вышел таймаут соединения если errno = None, иначе обрыв соединения.
                except OSError as error:
                    if error.errno:
                        CLIENT_LOGGER.critical(f'Потеряно соединение с сервером.')
                        break
                # Проблемы с соединением
                except (ConnectionError, ConnectionAbortedError, ConnectionResetError, json.JSONDecodeError):
                    CLIENT_LOGGER.critical(f'Потеряно соединение с сервером.')
                    break
                # Если пакет корретно получен выводим в консоль и записываем в базу.
                else:
                    if ACTION in message and message[
                        ACTION] == MESSAGE and SENDER in message and TARGET in message \
                            and MESSAGE_TEXT in message and message[TARGET] == self.account_name:
                        print(f'\nПолучено сообщение от пользователя {message[SENDER]}:\n{message[MESSAGE_TEXT]}')
                        # Захватываем работу с базой данных и сохраняем в неё сообщение
                        with database_lock:
                            try:
                                self.database.save_message(message[SENDER], self.account_name,
                                                           message[MESSAGE_TEXT])
                            except:
                                CLIENT_LOGGER.error('Ошибка взаимодействия с базой данных')

                        CLIENT_LOGGER.info(
                            f'Получено сообщение от пользователя {message[SENDER]}:\n{message[MESSAGE_TEXT]}')
                    else:
                        CLIENT_LOGGER.error(f'Получено некорректное сообщение с сервера: {message}')


@log
def create_arg_parser():
    """Парсер аргументов командной строки"""
    parser = argparse.ArgumentParser()
    parser.add_argument('addr', default=DEFAULT_IP_ADDRESS, nargs='?')
    parser.add_argument('port', default=DEFAULT_PORT, type=int, nargs='?')
    parser.add_argument('-n', '--name', default=None, nargs='?')

    namespace = parser.parse_args(sys.argv[1:])
    server_ip = namespace.addr
    server_port = namespace.port
    client_name = namespace.name

    # проверим подходящий номер порта
    if not 1023 < server_port < 65536:
        CLIENT_LOGGER.critical(
            f'Попытка запуска клиента с неподходящим номером порта: {server_port}. '
            f'Допустимы адреса с 1024 до 65535. Клиент завершается.')
        exit(1)

    return server_ip, server_port, client_name


@log
def create_presence(account_name):
    """Функция генерирует запрос о присутствии клиента"""
    out = {
        ACTION: PRESENCE,
        TIME: time.time(),
        USER: {
            ACCOUNT_NAME: account_name
        }
    }
    CLIENT_LOGGER.debug(f'Сформировано {PRESENCE} сообщение для пользователя {account_name}')
    return out


@log
def process_ans(message):
    """
    Функция разбирает ответ сервера на сообщение о присутствии,
    возвращает 200, если все ОК или генерирует исключение при ошибке
    :return:
    """
    CLIENT_LOGGER.debug(f'Разбор приветственного сообщения от сервера: {message}')
    if RESPONSE in message:
        if message[RESPONSE] == 200:
            return '200 : OK'
        elif message[RESPONSE] == 400:
            raise ServerError(f'400 : {message[ERROR]}')
    raise ReqFieldMissingError(RESPONSE)


# Функция запрос контакт листа
def contacts_list_request(sock, name):
    CLIENT_LOGGER.debug(f'Запрос контакт листа для пользователя {name}')
    req = {
        ACTION: GET_CONTACTS,
        TIME: time.time(),
        USER: name
    }
    CLIENT_LOGGER.debug(f'Сформирован запрос {req}')
    send_message(sock, req)
    ans = get_message(sock)
    CLIENT_LOGGER.debug(f'Получен ответ {ans}')
    if RESPONSE in ans and ans[RESPONSE] == 202:
        return ans[LIST_INFO]
    else:
        raise ServerError


# Функция добавления пользователя в контакт лист
def add_contact(sock, username, contact):
    CLIENT_LOGGER.debug(f'Создание контакта {contact}')
    req = {
        ACTION: ADD_CONTACT,
        TIME: time.time(),
        USER: username,
        ACCOUNT_NAME: contact
    }
    send_message(sock, req)
    ans = get_message(sock)
    if RESPONSE in ans and ans[RESPONSE] == 200:
        pass
    else:
        raise ServerError('Ошибка создания контакта')
    print('Удачное создание контакта.')


# Функция запроса списка известных пользователей
def user_list_request(sock, username):
    CLIENT_LOGGER.debug(f'Запрос списка известных пользователей {username}')
    req = {
        ACTION: USERS_REQUEST,
        TIME: time.time(),
        ACCOUNT_NAME: username
    }
    send_message(sock, req)
    ans = get_message(sock)
    if RESPONSE in ans and ans[RESPONSE] == 202:
        return ans[LIST_INFO]
    else:
        raise ServerError


# Функция удаления пользователя из контакт листа
def remove_contact(sock, username, contact):
    CLIENT_LOGGER.debug(f'Создание контакта {contact}')
    req = {
        ACTION: REMOVE_CONTACT,
        TIME: time.time(),
        USER: username,
        ACCOUNT_NAME: contact
    }
    send_message(sock, req)
    ans = get_message(sock)
    if RESPONSE in ans and ans[RESPONSE] == 200:
        pass
    else:
        raise ServerError('Ошибка удаления клиента')
    print('Удачное удаление')


# Функция инициализатор базы данных. Запускается при запуске, загружает данные в базу с сервера.
def database_load(sock, database, username):
    # Загружаем список известных пользователей
    try:
        users_list = user_list_request(sock, username)
    except ServerError:
        CLIENT_LOGGER.error('Ошибка запроса списка известных пользователей.')
    else:
        database.add_users(users_list)

    # Загружаем список контактов
    try:
        contacts_list = contacts_list_request(sock, username)
    except ServerError:
        CLIENT_LOGGER.error('Ошибка запроса списка контактов.')
    else:
        for contact in contacts_list:
            database.add_contact(contact)


def main():
    # Сообщаем о запуске
    print('Консольный месседжер. Клиентский модуль.')

    # Загружаем параметры командной строки
    server_ip, server_port, client_name = create_arg_parser()

    # Если имя пользователя не было задано, необходимо запросить пользователя.
    if not client_name:
        client_name = input('Введите имя пользователя: ')
    else:
        print(f'Клиентский модуль запущен с именем: {client_name}')

    CLIENT_LOGGER.info(
        f'Запущен клиент с параметрами: адрес сервера: {server_ip}, '
        f'порт: {server_port}, '
        f'имя пользователя: {client_name}')

    # Инициализация сокета и сообщение серверу о нашем появлении
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Таймаут 1 секунда, необходим для освобождения сокета.
        sock.settimeout(1)

        sock.connect((server_ip, server_port))
        send_message(sock, create_presence(client_name))
        answer = process_ans(get_message(sock))
        CLIENT_LOGGER.info(f'Установлено соединение с сервером. Ответ сервера: {answer}')
        print(f'Установлено соединение с сервером.')
    except json.JSONDecodeError:
        CLIENT_LOGGER.error('Не удалось декодировать полученную Json строку.')
        exit(1)
    except ServerError as error:
        CLIENT_LOGGER.error(f'При установке соединения сервер вернул ошибку: {error.text}')
        exit(1)
    except ReqFieldMissingError as missing_error:
        CLIENT_LOGGER.error(f'В ответе сервера отсутствует необходимое поле {missing_error.missing_field}')
        exit(1)
    except (ConnectionRefusedError, ConnectionError):
        CLIENT_LOGGER.critical(
            f'Не удалось подключиться к серверу {server_ip}:{server_port},'
            f' конечный компьютер отверг запрос на подключение.')
        exit(1)
    else:
        # Инициализация БД
        database = ClientDatabase(client_name)
        database_load(sock, database, client_name)

        # Если соединение с сервером установлено корректно, запускаем поток взаимодействия с пользователем
        sender = ClientSender(client_name, sock, database)
        sender.daemon = True
        sender.start()
        CLIENT_LOGGER.debug('Запущены процессы')

        # затем запускаем поток - приёмник сообщений.
        receiver = ClientReader(client_name, sock, database)
        receiver.daemon = True
        receiver.start()

        # Watchdog основной цикл, если один из потоков завершён, то значит или потеряно соединение, или пользователь
        # ввёл exit. Поскольку все события обрабатываются в потоках, достаточно просто завершить цикл.
        while True:
            time.sleep(1)
            if receiver.is_alive() and sender.is_alive():
                continue
            break


if __name__ == '__main__':
    main()
