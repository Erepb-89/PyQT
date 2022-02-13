"""
1.	Написать функцию host_ping(), в которой с помощью утилиты ping будет проверяться доступность сетевых узлов.
Аргументом функции является список, в котором каждый сетевой узел должен быть представлен именем хоста или ip-адресом.
В функции необходимо перебирать ip-адреса и проверять их доступность с выводом соответствующего сообщения
(«Узел доступен», «Узел недоступен»). При этом ip-адрес сетевого узла должен создаваться с помощью функции ip_address().
"""
from subprocess import Popen, PIPE
from ipaddress import ip_address
import socket


def host_ping(address_list, timeout, requests):
    enabled_nodes = []
    disabled_nodes = []
    for address in address_list:
        trans_address = ip_address(socket.gethostbyname(address))

        process = Popen(f"ping {trans_address} -w {timeout} -n {requests}", shell=False, stdout=PIPE)
        process.wait()
        returned_code = process.returncode

        str_adr = f"Узел {address}" if str(address) == str(trans_address) else f"Узел {address} ({trans_address})"

        if returned_code == 1:
            disabled_nodes.append(str(trans_address))
            print(str_adr, "недоступен")
        if returned_code == 0:
            enabled_nodes.append(str(trans_address))
            print(str_adr, "доступен")

    res = {
        "Доступные узлы": enabled_nodes,
        "Недоступные узлы": disabled_nodes,
    }
    return res


if __name__ == "__main__":
    ip_address_list = ["google.com", "8.8.8.8", "yandex.ru", "192.168.232.1", "192.168.0.1"]
    nodes_dict = host_ping(ip_address_list, 1000, 1)
    print(nodes_dict)
