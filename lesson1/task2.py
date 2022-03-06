"""
2.	Написать функцию host_range_ping() для перебора ip-адресов из заданного диапазона.
Меняться должен только последний октет каждого адреса.
По результатам проверки должно выводиться соответствующее сообщение.
"""
from task1 import host_ping
from ipaddress import ip_address


def address_query():
    while True:
        new_ip = input("Введите начальный ip-адрес: ")
        try:
            checked_ip = ip_address(new_ip)
            octet = int(new_ip.split(".")[3])
            break
        except Exception as error:
            print(error)
    return checked_ip, octet


def host_range_ping():
    ip, last_octet = address_query()
    while True:
        try:
            num = int(input("Какое количество ip-адресов надо проверить: "))
            break
        except Exception as error:
            print(error)
    if num > 255 or num + last_octet > 255:
        num = 255 - last_octet
    new_list = [str(ip + i) for i in range(num)]
    print(new_list)
    result = host_ping(new_list, 1000, 1)
    return result


if __name__ == "__main__":
    host_range_ping()
