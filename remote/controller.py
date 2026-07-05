"""
remote/controller.py

Receives commands remotely (Pause, Resume, Stop) from the operator over Telegram or Discord.
"""


class RemoteController:
    """
    Listens for control signals from remote API endpoints or message queues.
    """

    def __init__(self, token: str) -> None:
        """Initializes the RemoteController."""
        self.token = token

    def check_commands(self) -> list:
        """
        Polls or checks for pending commands.

        Returns:
            list: List of pending command strings.
        """
        return []
