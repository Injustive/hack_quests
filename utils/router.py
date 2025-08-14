import importlib
from functools import partial
from .utils import get_projects
import inquirer
from termcolor import colored
from inquirer.themes import load_theme_from_dict as loadth
from abc import ABC, abstractmethod
from .run_config import current_run, ROOT_DIR
import os
from .config import CONFIG


class MainRouter(ABC):
    def __init__(self):
        self.choices = self.get_choices()

    def get_action(self):
        theme = {
            'Question': {
                'brackets_color': 'bright_yellow'
            },
            'List': {
                'selection_color': 'bright_blue'
            },
        }

        question = [
            inquirer.List(
                "action",
                message=colored('Select:', 'light_yellow'),
                choices=self.choices
            )
        ]
        return inquirer.prompt(question, theme=loadth(theme))['action']

    @abstractmethod
    def get_choices(self):
        pass


class Router(MainRouter):
    def __init__(self, module: str):
        self.module = module
        super().__init__()

    def get_choices(self):
        projects = get_projects(self.module)
        utils = f'   utils'
        return [f'   {i}) {project.split("run_")[1].title()}' for i, project in enumerate(projects, 1)] + [utils]

    @staticmethod
    def main_runner(package: str):
        if 'utils' in package:
            from .modules.main import run as utils_run
            utils_run()
        else:
            formatted_package = 'run_' + package.split()[-1].lower()
            current_run.PACKAGE = formatted_package
            main = importlib.import_module('.main', package=formatted_package)
            main.runner.run()

    def route(self):
        action = self.get_action()
        return dict(zip(self.choices, [partial(self.main_runner, action)]*len(self.choices)))[action]()


class DbRouter:
    def __init__(self):
        self.db = None

    def choose_action(self):
        theme = {
            'Question': {
                'brackets_color': 'bright_yellow'
            },
            'List': {
                'selection_color': 'bright_blue'
            },
        }

        question = [
            inquirer.List(
                "action",
                message=colored('Select database:', 'light_yellow'),
                choices=self.choose_db()
            )
        ]
        return inquirer.prompt(question, theme=loadth(theme))['action']

    def choose_db(self,):
        dbs_path = os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'database')
        dbs = [f for f in os.listdir(dbs_path) if f.endswith(".db")] + ['new']
        return dbs

    def start_db_router(self):
        self.db = self.choose_action()


class UtilsDbRouter(DbRouter):
    def __init__(self):
        super().__init__()
        self.pkg_name = None

    def choose_db(self):
        dbs_path = os.path.join(ROOT_DIR, 'data', 'database', self.pkg_name)
        os.makedirs(dbs_path, exist_ok=True)
        dbs = [f for f in os.listdir(dbs_path) if f.endswith(".db")] + ['new']
        return dbs