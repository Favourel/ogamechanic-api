import smtplib

from django.core.mail.backends.smtp import EmailBackend


class CustomEmailBackend(EmailBackend):
    def __init__(
            self,
            host=None,
            port=None,
            username=None,
            password=None,
            use_tls=None,
            fail_silently=False,
            use_ssl=None,
            timeout=None,
            ssl_keyfile=None,
            ssl_certfile=None,
            **kwargs,
    ):
        super().__init__(host, port, username, password, use_tls, 
                         fail_silently, use_ssl, timeout, ssl_keyfile,
                         ssl_certfile, **kwargs)
        self.source_address = None
        self.local_hostname = None

    def _send(self, email_message):
        """A helper method that does the actual sending."""
        if not email_message.recipients():
            return False
        try:
            self.open()
            if not self.connection:
                # We failed silently on open(). Mark this message as not sent
                # so it can be retried later.
                return False
            self.connection.sendmail(
                email_message.from_email,
                email_message.recipients(),
                email_message.message().as_bytes(linesep='\r\n'),
            )
        except smtplib.SMTPException:
            if not self.fail_silently:
                raise
            return False
        return True

    def open(self):
        """
        Ensure we have a connection to the email server. Return whether or not
        a new connection was required (True or False) to facilitate test
        mocking.
        """
        if self.connection:
            return False

        connection_params = self.get_connection_params()
        try:
            self.connection = self.connection_class(**connection_params)
            # TLS/SSL are mutually exclusive, so only attempt TLS over
            # non-secure connections.
            if not self.use_ssl and self.use_tls:
                self.connection.starttls()  # Remove keyfile and certfile
            if self.username and self.password:
                self.connection.login(self.username, self.password)
        except smtplib.SMTPException:
            if not self.fail_silently:
                raise
            return False
        return True

    def get_connection_params(self):
        """Get connection parameters for smtp server"""
        params = {
            'host': self.host,
            'port': self.port,
            'local_hostname': self.local_hostname,
            'timeout': self.timeout,
            'source_address': self.source_address,
        }
        return params
