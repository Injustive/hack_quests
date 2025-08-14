from typing import Optional, Literal
import uuid

from pydantic import BaseModel


Status = Literal['idle', 'processing', 'ready', 'error']


class BasePayload(BaseModel):
    def json(self):
        return self.model_dump(exclude_none=True)


class CaptchaTaskMetadata(BasePayload):
    action: str = ''
    cdata: Optional[str] = None


class CaptchaTask(BasePayload):
    id: str = None
    type: str
    websiteURL: str
    websiteKey: str
    metadata: Optional[CaptchaTaskMetadata] = None


class CaptchaCreateTaskPayload(BasePayload):
    clientKey: str
    task: CaptchaTask


class CaptchaGetTaskPayload(BasePayload):
    clientKey: str
    taskId: str


class CaptchaSolution(BasePayload):
    token: str
    type: str = 'AntiTurnstileTaskProxyLess'


class CaptchaTaskResponse(BasePayload):
    errorId: int = 0
    errorDescription: Optional[str] = None
    taskId: Optional[str] = None
    status: Status = 'error'
    solution: Optional[CaptchaSolution] = None
