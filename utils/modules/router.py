from utils.router import MainRouter
import os
import importlib
from functools import partial


class UtilsRouter(MainRouter):
    def get_choices(self):
        current_directory = os.path.dirname(os.path.abspath(__file__))
        return [f[6:] for f in os.listdir(current_directory) if f.startswith('utils_')]

    @staticmethod
    def main_runner(package: str):
        formatted_package = 'utils.modules.utils_' + package.split()[-1].lower()
        main = importlib.import_module('.main', package=formatted_package)
        main.run()

    def route(self):
        action = self.get_action()
        return dict(zip(self.choices, [partial(self.main_runner, action)]*len(self.choices)))[action]()

    @property
    def action(self):
        return self.get_action()
