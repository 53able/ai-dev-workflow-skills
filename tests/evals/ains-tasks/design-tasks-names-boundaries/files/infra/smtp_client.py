"""メール送信。社内の SMTP リレーへ送る。"""
from email.message import EmailMessage
import smtplib


class SmtpError(Exception):
    """メールを送れなかった。"""


class SmtpClient:
    def __init__(self, host: str = 'localhost', port: int = 25, sender: str = 'shop@example.com'):
        self.host = host
        self.port = port
        self.sender = sender

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg['From'] = self.sender
        msg['To'] = to
        msg['Subject'] = subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as e:
            raise SmtpError(str(e)) from e
