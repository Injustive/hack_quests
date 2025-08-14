import re
import ssl
import asyncio
from time import process_time_ns
from typing import Optional
from datetime import datetime, timedelta
import pytz
from imap_tools import MailBox, MailboxLoginError
from imaplib import IMAP4_SSL


class MailBoxClient(MailBox):
    def __init__(
        self,
        host: str,
        *,
        proxy = None,
        port: int = 993,
        timeout: float = None,
        ssl_context=None,
    ):
        self._proxy = proxy
        super().__init__(host=host, port=port, timeout=timeout, ssl_context=ssl_context)

    def _get_mailbox_client(self):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        if self._proxy:
            return IMAP4_SSL(
                self._proxy.host,
                port=self._proxy.port,
                timeout=self._timeout,
                ssl_context=ssl_context,
            )
        else:
            return IMAP4_SSL(
                self._host,
                port=self._port,
                timeout=self._timeout,
                ssl_context=ssl_context,
            )


class AsyncEmailChecker:
    def __init__(self, email: str, password: str, logger):
        self.email = email
        self.password = password
        self.imap_server = self._get_imap_server(email)
        self.search_start_time = datetime.now(pytz.UTC)
        self.logger = logger

    def _get_imap_server(self, email: str) -> str:
        """Returns the IMAP server based on the email domain."""
        if email.endswith("@rambler.ru"):
            return "imap.rambler.ru"
        elif email.endswith("@gmail.com"):
            return "imap.gmail.com"
        elif "@gmx." in email:
            return "imap.gmx.com"
        elif "outlook" in email:
            return "imap-mail.outlook.com"
        elif email.endswith("@mail.ru"):
            return "imap.mail.ru"
        else:
            return "imap.firstmail.ltd"

    async def print_all_messages(self, proxy = None) -> None:
        """Prints all messages in the mailbox"""
        self.logger.info(f"Account: {self.email} | Printing all messages...")
        try:

            def print_messages():
                with MailBoxClient(self.imap_server, proxy=proxy, timeout=30).login(
                    self.email, self.password
                ) as mailbox:
                    for msg in mailbox.fetch():
                        print("\n" + "=" * 50)
                        print(f"From: {msg.from_}")
                        print(f"To: {msg.to}")
                        print(f"Subject: {msg.subject}")
                        print(f"Date: {msg.date}")
                        print("\nBody:")
                        print(msg.text or msg.html)

            await asyncio.to_thread(print_messages)
        except Exception as error:
            self.logger.error(f"Account: {self.email} | Failed to fetch messages: {error}")

    async def check_if_email_valid(self, proxy = None) -> bool:
        try:

            def validate():
                with MailBoxClient(self.imap_server, proxy=proxy, timeout=30).login(
                    self.email, self.password
                ):
                    return True

            await asyncio.to_thread(validate)
            return True
        except Exception as error:
            self.logger.error(f"Account: {self.email} | Email is invalid (IMAP): {error}")
            return False

    def _search_for_pattern(
        self, mailbox: MailBox, pattern: str | re.Pattern, is_regex: bool = True
    ) -> Optional[str]:
        """Searches for pattern in mailbox messages"""
        time_threshold = self.search_start_time - timedelta(seconds=60)

        messages = sorted(
            mailbox.fetch(),
            key=lambda x: (
                x.date.replace(tzinfo=pytz.UTC) if x.date.tzinfo is None else x.date
            ),
            reverse=True,
        )

        for msg in messages:
            msg_date = (
                msg.date.replace(tzinfo=pytz.UTC)
                if msg.date.tzinfo is None
                else msg.date
            )

            if msg_date < time_threshold:
                continue

            body = msg.text or msg.html
            if not body:
                continue
            if is_regex:
                if isinstance(pattern, str):
                    pattern = re.compile(pattern)
                match = pattern.search(body)
                if match:
                    return match.group(0)
            else:
                if pattern in body:
                    return pattern

        return None

    def _search_for_pattern_in_spam(
        self,
        mailbox: MailBox,
        spam_folder: str,
        pattern: str | re.Pattern,
        is_regex: bool = True,
    ) -> Optional[str]:
        """Searches for pattern in spam folder"""
        if mailbox.folder.exists(spam_folder):
            mailbox.folder.set(spam_folder)
            return self._search_for_pattern(mailbox, pattern, is_regex)
        return None

    async def check_email_for_verification_link(
        self,
        pattern: (
            str | re.Pattern
        ) = r'http://loyalty\.campnetwork\.xyz/verify-account\?token=[^\s"\'<>]+',
        is_regex: bool = True,
        max_attempts: int = 20,
        delay_seconds: int = 3,
        proxy = None,
    ) -> Optional[str]:
        """
        Searches for a pattern in email messages.

        Args:
            pattern: String or regex pattern to search for
            is_regex: If True, treats pattern as regex, otherwise as plain text
            max_attempts: Maximum number of attempts to search
            delay_seconds: Delay between attempts in seconds
            proxy: Optional proxy to use

        Returns:
            Found pattern or None if not found
        """
        try:
            for attempt in range(max_attempts):

                def search_inbox():
                    with MailBoxClient(self.imap_server, proxy=proxy, timeout=30).login(
                        self.email, self.password
                    ) as mailbox:
                        return self._search_for_pattern(mailbox, pattern, is_regex)

                result = await asyncio.to_thread(search_inbox)
                if result:
                    return result
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay_seconds)

            # Check spam folders
            self.logger.warning(
                f"Account: {self.email} | Pattern not found after {max_attempts} attempts, searching in spam folder..."
            )
            spam_folders = ("SPAM", "Spam", "spam", "Junk", "junk", "Spamverdacht")

            def search_spam():
                with MailBoxClient(self.imap_server, proxy=proxy, timeout=30).login(
                    self.email, self.password
                ) as mailbox:
                    for spam_folder in spam_folders:
                        result = self._search_for_pattern_in_spam(
                            mailbox, spam_folder, pattern, is_regex
                        )
                        if result:
                            self.logger.success(
                                f"Account: {self.email} | Found pattern in spam"
                            )
                            return result
                return None

            result = await asyncio.to_thread(search_spam)
            if result:
                return result

            self.logger.error(f"Account: {self.email} | Pattern not found in any folder")
            return None

        except Exception as error:
            self.logger.error(
                f"Account: {self.email} | Failed to check email for pattern: {error}"
            )
            return None
