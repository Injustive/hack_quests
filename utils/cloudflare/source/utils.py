# -*- coding: utf-8 -*-

from time import time, sleep
from threading import Thread, Lock
import random
import json
import sys
import os


LOGO = """
╔══╗─╔══╗╔════╗╔══╗────╔══╗╔══╗╔═══╗╔═══╗╔═══╗
║╔╗║─║╔╗║╚═╗╔═╝║╔═╝────║╔═╝║╔╗║║╔═╗║║╔══╝║╔══╝
║╚╝╚╗║║║║──║║──║╚═╗╔══╗║╚═╗║║║║║╚═╝║║║╔═╗║╚══╗
║╔═╗║║║║║──║║──╚═╗║╚══╝║╔═╝║║║║║╔╗╔╝║║╚╗║║╔══╝
║╚═╝║║╚╝║──║║──╔═╝║────║║──║╚╝║║║║║─║╚═╝║║╚══╗
╚═══╝╚══╝──╚╝──╚══╝────╚╝──╚══╝╚╝╚╝─╚═══╝╚═══╝
https://t.me/bots_forge
"""


class ResThread(Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.result = None

    def run(self):
        try:
            if self._target is not None:
                self.result = self._target(*self._args, **self._kwargs)
        finally:
            del self._target, self._args, self._kwargs


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class Cached(type):
    """
    class Foo(metaclass=Cached):
        def __init__(self, n):
            self.n = n
    a = Foo(5)
    b = Foo(5)
    c = Foo(6)
    print(id(a) == id(b))
    # >>> True
    print(id(a) == id(c))
    # >>> False
    """
    _instances = dict()
    _locks = dict()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._locks:
            cls._locks[cls] = Lock()
        with cls._locks[cls]:
            input_ = (str(args), str(kwargs))
            if cls not in cls._instances:
                cls._instances[cls] = dict()
            if input_ not in cls._instances[cls]:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls][input_] = instance
            return cls._instances[cls][input_]


def tcached(t: int = None):
    _instances = dict()

    def wrapper(func):
        def inner(*args, _ignore_tcache=False, **kwargs):
            input_ = (str(args), str(kwargs))
            if input_ not in _instances:
                _instances[input_] = (func(*args, **kwargs), time())
            elif (t and _instances[input_][1] + t < time()) or _ignore_tcache:
                _instances[input_] = (func(*args, **kwargs), time())
            return _instances[input_][0]
        return inner
    return wrapper


def cached(func):
    _instances = dict()

    def wrapper(*args, **kwargs):
        input_ = (str(args), str(kwargs))
        if input_ not in _instances:
            _instances[input_] = func(*args, **kwargs)
        return _instances[input_]
    return wrapper


def get_rnd_value(values: list) -> int:
    if len(values) == 1:
        return values[0]
    else:
        values.sort()
        return random.randint(*values)


def rnd_sleep(values: list):
    sleep(get_rnd_value(values))


def jprint(json_):
    print(json.dumps(json_, indent=4, ensure_ascii=False, default=str))


def resource_path(relative):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    else:
        return os.path.join(os.path.abspath("."), relative)


def test():
    pass


if __name__ == '__main__':
    test()
