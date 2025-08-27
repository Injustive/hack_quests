# -*- coding: utf-8 -*-

from collections import defaultdict
from typing import Sequence, Union, Dict
from loguru import logger
from threading import Lock

from .errors import ConfigError


__all__ = (
    'AbsConfig',
    'ConfigError'
)


class AbsConfig(defaultdict):
    """
    Сразу загружает с файла и делает проверку по шаблону
    Если в конфиге лишние пары - паттерн их игнорирует.
    В ключе паттерна указываем какой ключ должен быть в конфиге,
    а в value таке варианты:
        self.pattern = {
            'a1': [True, ''],
            'a2': [True, None],
            'a3': [True, ()],
            'a4': [True],  # во всех выше случаях будет проводиться только проверка ключа
            'a41': [False, int]  # ключ не обязателен, но будет приведен к инт, если будет передан
            'a5': [True, int],
            'a6': [True, str],
            'a7': [True, int, lambda x: x % 2 == 0],
            'a8': (True, lampda x: round(float(x), 5), (lampda x: x > 3, 'Value must be > 3')),
            'a9': [True, str, (), (lambda x: len(x) == 10, 'Value length must be 10')]
            'a10': [True, (lambda x: int(x) * 10, 'int')],  # можно указать сообщение каким должно быть значение
        }
    Суть в том, что под ключем будет записан результат первой в списке функции, примененной к изначальному значению.
    Если нет первой функции, то ничего применться не будет
    Первый аргумент должен быть True или False отвечающий за обязательность ключа.
    Затем к уже обработанное значение будет поочередно передано во все остальные функции в последовательности.
        Функция может указываться как fn, (fn) или (fn, message)
        Функции должны возвращать True или False. Если вернется False - будет поднято исключение с сообщением message
    Во всех случаях ожидаемых исключений поднимается исключение ConfigError.
    """

    def __init__(self, pattern, source: Union[Dict, str]):
        super().__init__()
        self.filename = None
        self.lock = Lock()
        self.pattern = pattern
        if isinstance(source, str):
            self.filename = source
            self.read_config()
        elif isinstance(source, dict):
            self.update(source)
        else:
            raise ConfigError('Wrong source')
        self.check_self()
        self.__dict__.update(self)

    def read_config(self, filename=None):
        filename = filename or self.filename
        try:
            with open(filename, encoding='utf-8') as file:
                data = file.read()
            if data and data[0] == '\ufeff':
                with open(filename, encoding='utf-8-sig') as file:
                    data = file.read()

            data = data.split('\n')
            new_data = dict()
            for line in data:
                if '===' in line:
                    line = [i.strip() for i in line.strip().split('===')]
                    try:
                        if line[1] and line[0] in self.pattern:
                            new_data[line[0]] = line[1]
                    except IndexError:
                        pass
        except FileNotFoundError:
            logger.error('Нет файла config или файл заполнен неверно')
            raise ConfigError
        self.update(new_data)
        logger.info('read config successfully')
        return new_data

    def check_self(self):
        for key, value in self.pattern.items():
            if not isinstance(value, Sequence):
                value = [value]
            if not self.get(key):
                if value[0]:
                    raise ConfigError(f'KeyError: missing {key}')
                else:
                    continue

            if len(value) == 1:
                continue

            fn = value[1]
            message = None
            if isinstance(fn, Sequence):
                if len(fn) > 1:
                    message = fn[1]
                    fn = fn[0]
                elif len(fn) > 0:
                    fn = fn[0]
                else:
                    continue
            try:
                self[key] = fn(self[key])
            except Exception:
                raise ConfigError(f'Invalid value "{self[key]}" in key "{key}". Value type must be {message or fn}')
            if len(value) > 2:
                for fn in value[2:]:
                    message = ''
                    if isinstance(fn, Sequence):
                        if len(fn) > 1:
                            message = fn[1]
                            fn = fn[0]
                        elif len(fn) > 0:
                            fn = fn[0]
                        else:
                            continue
                    if not fn(self[key]):
                        raise ConfigError(f'Invalid {key} value "{self[key]}". {message}')

    def __str__(self):
        return str(dict(self))


def test():
    c = Config()
    print(c)


if __name__ == '__main__':
    test()
