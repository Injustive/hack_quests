from utils.router import MainRouter, DbRouter


class HackQuestsRouter(MainRouter, DbRouter):
    def get_choices(self):
        return ['Registration',
                'Write ref codes',
                'Start daily']

    def route(self, task, action):
        return dict(zip(self.get_choices(), [task.registration,
                                             task.write_ref_codes,
                                             task.infinity_run_daily]))[action]

    @property
    def action(self):
        self.start_db_router()
        return self.get_action()
