class GalxeVerificationException(Exception):
    def __init__(self, message=None):
        if message is None:
            self.message = "Galxe verification failed"
        else:
            self.message = message
        super().__init__(self.message)


class EmailVerificationException(Exception):
    pass


class TwitterException(Exception):
    def __init__(self, message=None):
        if message is None:
            self.message = "Twitter error"
        else:
            self.message = message
        super().__init__(self.message)
