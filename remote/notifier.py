"""
remote/notifier.py

Provides outbound communication channels (Telegram, Discord) to send status reports,
alerts, and screenshots to the operator.
"""


class RemoteNotifier:
    """
    Sends execution updates and screenshot attachments via webhooks or bot APIs.
    """

    def __init__(self, token: str, chat_id: str) -> None:
        """Initializes the RemoteNotifier."""
        self.token = token
        self.chat_id = chat_id

    def send_alert(self, message: str, image_path: str = "") -> None:
        """Sends an alert message to the user."""
        pass
