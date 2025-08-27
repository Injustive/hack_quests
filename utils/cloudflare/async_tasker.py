import asyncio
from time import time
from typing import Optional
import traceback

from loguru import logger

from .browser import Browser
from .models import CaptchaTask, CaptchaTaskResponse


class Tasker:
    tasks = {}
    results = []

    def __init__(self, max_workers: int = 1, callback_fn=None):
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
        self.callback_fn = callback_fn
        self._last_clear = time()

    async def add_task(self, task: CaptchaTask) -> None:
        r = await self._add_task(task)
        if isinstance(r, CaptchaTaskResponse):
            if self.callback_fn:
                self.callback_fn(r)
            else:
                self.results.append(r)

    async def _add_task(self, task: CaptchaTask) -> Optional[CaptchaTaskResponse]:
        try:
            if isinstance(task, dict):
                task = CaptchaTask(**task)

            if len(self.tasks) > self.max_workers * 2:
                logger.warning(f'overloaded, tasks={len(self.tasks)}, workers={self.max_workers}')
                return CaptchaTaskResponse(
                    status='error',
                    taskId=task.id,
                    errorId=1, errorDescription='The solver is overloaded')

            self.tasks[task.id] = {'t': time(), 'task': task}
            # loop = asyncio.get_running_loop()
            await self.solve(task)

        except Exception as er:
            logger.warning(er)
            if self.tasks[task.id]:
                del self.tasks[task.id]
            try:
                return CaptchaTaskResponse(
                    status='error', taskId=task.id, errorId=1, errorDescription=f'{er.__class__.__name__}: {er}')
            except Exception:
                pass

    async def solve(self, task: CaptchaTask):
        try:
            async with self.semaphore:
                if token := await Browser().solve_captcha(task):
                    r = CaptchaTaskResponse(
                        taskId=task.id,
                        status='ready',
                        solution={
                            'token': token,
                            'type': task.type})
                else:
                    r = CaptchaTaskResponse(
                        taskId=task.id,
                        status='error',
                        errorId=1,
                        errorDescription=f'token not found')

        except Exception as er:
            r = CaptchaTaskResponse(
                taskId=task.id,
                status='error',
                errorId=1,
                errorDescription=f'{er.__class__.__name__}: {er}')
            logger.warning(f"{er.__class__.__name__}: {er}")
            logger.debug(traceback.format_exc())
        finally:
            del self.tasks[task.id]

        if self.callback_fn:
            self.callback_fn(r)
        else:
            self.results.append(r)
