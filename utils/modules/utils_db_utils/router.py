from utils.router import MainRouter
import os
from utils.run_config import ROOT_DIR


class DbUtilsRouter(MainRouter):
    def get_choices(self):
        return ['merge']


class ProjectSelectRouter(MainRouter):
    def get_choices(self):
        projects = [f for f in os.listdir(ROOT_DIR) if f.startswith('run_')]
        return [f'   {i}) {project.split("run_")[1].title()}' for i, project in enumerate(projects, 1)]

class ProjectDbSelectRouter(MainRouter):
    def __init__(self, project, excludes=None):
        self.project = project
        self.excludes = [] if excludes is None else excludes
        super().__init__()

    def get_choices(self):
        dbs_path = os.path.join(ROOT_DIR, self.project, 'data', 'database')
        dbs = [f for f in os.listdir(dbs_path) if f.endswith(".db")]
        if len(dbs) < 2:
            raise KeyError
        dbs = [db for db in dbs if db not in self.excludes]
        return dbs
