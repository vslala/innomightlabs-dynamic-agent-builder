"""Account invitation mail. The owning lifecycle keeps and rotates the secret."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .message import EmailLink, MessageEmail, render_email_template

INVITATION_DELIVERY_FAILED = "Account invitation email delivery failed"


@dataclass(frozen=True)
class AccountInvitationEmail:
    account_name: str
    invited_by: str
    invite_url: str = field(repr=False)
    expires_at: str

    def __post_init__(self) -> None:
        # Autoescaping cannot make an unsafe URL scheme safe. The route owns origin/path construction.
        url = urlsplit(self.invite_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or "\\" in self.invite_url
            or any(character.isspace() or ord(character) < 32 or ord(character) == 127
                   for character in self.invite_url)
        ):
            raise ValueError("Invalid invitation URL")
        # Accessing port also rejects malformed port values without including the URL in our error.
        try:
            url.port
        except ValueError:
            raise ValueError("Invalid invitation URL") from None

    @property
    def subject(self) -> str:
        return "You're invited to an InnomightLabs account"

    def _message(self) -> MessageEmail:
        # invited_by is an immutable user ID, not a display name; never expose it in recipient copy.
        return MessageEmail(
            heading="You're invited to join an account",
            preheader="Accept your account invitation on InnomightLabs.",
            paragraphs=[f"You've been invited to join {self.account_name} on InnomightLabs."],
            details=[("Invitation expires", self.expires_at)],
            closing=["If you weren't expecting this invitation, you can ignore this email."],
            action=EmailLink("Accept invitation", self.invite_url),
            footer=EmailLink("InnomightLabs", "https://innomightlabs.com"),
        )

    def html(self) -> str:
        return render_email_template("account_invitation.html", email=self._message())

    def text(self) -> str:
        return self._message().text()
