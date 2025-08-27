class BotError(Exception):
    pass


class BrowserError(BotError):
    pass


class BrowserCreateError(BrowserError):
    pass


class BrowserNotFoundError(BrowserError):
    pass


class BrowserFlowError(BrowserError):
    pass


class ConfigError(BotError):
    pass


class WebRequestError(BotError):
    pass


class UsernameNotFound(BotError):
    pass


class LicenseError(BotError):
    pass
