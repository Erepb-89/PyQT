"""
3.	Написать функцию host_range_ping_tab(), возможности которой основаны на функции из примера 2.
Но в данном случае результат должен быть итоговым по всем ip-адресам, представленным в табличном формате
(использовать модуль tabulate). Таблица должна состоять из двух колонок и выглядеть примерно так:

"""
from task2 import host_range_ping
from tabulate import tabulate


def host_range_ping_tab():
    nodes_dict = host_range_ping()
    print(tabulate(nodes_dict, headers='keys', tablefmt="grid", stralign="center"))


if __name__ == "__main__":
    host_range_ping_tab()
