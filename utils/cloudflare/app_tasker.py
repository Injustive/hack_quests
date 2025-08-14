import uuid
import os
from time import time
from typing import Union

from loguru import logger

from .models import CaptchaCreateTaskPayload, CaptchaTaskResponse, CaptchaTask, CaptchaSolution, CaptchaGetTaskPayload


class Tasker:
    tasks = {}
    results = {}
    _last_clear = time()

    solvers = {'AntiTurnstileTaskProxyLess': None}

    @classmethod
    def add_task(cls, payload: CaptchaCreateTaskPayload) -> CaptchaTaskResponse:
        try:
            if isinstance(payload, dict):
                payload = CaptchaCreateTaskPayload(**payload)
            elif isinstance(payload, CaptchaCreateTaskPayload):
                pass
            else:
                raise ValueError('Wrong payload')

            if not cls.solvers.get('AntiTurnstileTaskProxyLess'):
                return CaptchaTaskResponse(status='error', errorId=1, errorDescription='Service temporary unavailable')

            # if payload.clientKey != os.getenv('API_KEY'):
            #     return CaptchaTaskResponse(status='error', errorId=1, errorDescription='Wrong clientKey')

            if payload.task.type not in ('AntiTurnstileTaskProxyLess', ):
                return CaptchaTaskResponse(status='error', errorId=1, errorDescription='Unsupported captcha type')

            payload.task.id = str(uuid.uuid4())
            cls.tasks[payload.task.id] = {'t': time(), 'task': payload.task}

            if cls._last_clear + 30 < time():
                cls.clear_expired()

            return CaptchaTaskResponse(status='idle', taskId=payload.task.id)

        except Exception as er:
            return CaptchaTaskResponse(status='error', errorId=1, errorDescription=f"{er.__class__.__name__}: {er}")

    @classmethod
    def add_result(cls, result: CaptchaTaskResponse):
        try:
            if isinstance(result, dict):
                result = CaptchaTaskResponse(**result)
            if result.taskId in cls.tasks:
                del cls.tasks[result.taskId]
                cls.results[result.taskId] = {'t': time(), 'result': result}
            else:
                raise ValueError(f"taskId {result.taskId} not exists")
        finally:
            if cls._last_clear + 30 < time():
                cls.clear_expired()

    @classmethod
    def get_result(cls, payload: CaptchaGetTaskPayload) -> CaptchaTaskResponse:
        try:
            if isinstance(payload, dict):
                payload = CaptchaGetTaskPayload(**payload)

            # if payload.clientKey != os.getenv('API_KEY'):
            #     return CaptchaTaskResponse(status='error', errorId=1, errorDescription='Wrong clientKey')

            if payload.taskId in cls.results:
                return cls.results[payload.taskId]['result']

            if payload.taskId in cls.tasks:
                return CaptchaTaskResponse(status='processing', taskId=payload.taskId)

            return CaptchaTaskResponse(
                status='error',
                errorId=1, errorDescription='Response expired or task not exists',
                taskId=payload.taskId)

        except Exception as er:
            return CaptchaTaskResponse(status='error', errorId=1, errorDescription=f"{er.__class__.__name__}: {er}")
        finally:
            if cls._last_clear + 30 < time():
                cls.clear_expired()

    @classmethod
    def clear_expired(cls, task_timeout: int = 120, result_timeout: int = 5 * 60) -> None:
        now = time()
        for id_ in list(cls.tasks.keys()):
            if cls.tasks[id_]['t'] + task_timeout < now:
                result = CaptchaTaskResponse(errorId=1, errorDescription='Task expired', taskId=id_)
                cls.results[id_] = {'t': now, 'result': result}
                del cls.tasks[id_]
                logger.debug(f"task {id_} expired")

        for id_ in list(cls.results.keys()):
            if cls.results[id_]['t'] + result_timeout < now:
                del cls.results[id_]
                logger.debug(f"deleted result for task {id_} by timeout")

        cls._last_clear = time()

    @classmethod
    def add_solver(cls, solver_type: str, sid):
        cls.solvers[solver_type] = sid

    @classmethod
    def remove_solver(cls, sid):
        for k, v in list(cls.solvers.items()):
            if v == sid:
                cls.solvers[k] = None
