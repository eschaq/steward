"""Outbound email over Gmail SMTP — invitations, and the two moments a family
needs to hear about without opening the app.

A courtesy on top of the membership record, never a gate in front of it. The
EstateMembership row is the source of truth about who has been asked to an
estate; this module only tries to tell them. Every failure here — no
credentials, a rejected login, a dropped connection — comes back as a result
object saying plainly what happened, and the invite stands regardless. That is
CLAUDE.md's failure-handling principle applied to the one part of the system
that talks to the outside world.

Gmail, deliberately: an app password in `.env` and nothing else to sign up for.
`python-dotenv` was dropped from this project when classification moved to
Vertex AI, so `.env` is read here directly rather than reinstating it for two
keys.
"""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import NamedTuple, Optional

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_TIMEOUT = 20

# Who the email says it is from. Not the Gmail account's own display name — the
# person receiving this has never heard of it.
FROM_NAME = "Steward"

ENV_PATH = Path(__file__).with_name(".env")


def load_env(path: Path = ENV_PATH) -> None:
    """Read `.env` into the environment, without overwriting what is already set.

    Deliberately small: `KEY=value` lines, `#` comments, optional surrounding
    quotes. A real process environment (Cloud Run, a shell export) always wins,
    so this file is a local convenience and never a source of surprise in
    production.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


class SendResult(NamedTuple):
    """What actually happened, in words the executor can be shown.

    `sent` is the only thing the UI branches on; `note` is what it says out
    loud. There is no exception path — a failed email must not take an invite
    down with it.
    """

    sent: bool
    note: str


NO_CREDENTIALS = (
    "No email was sent — this copy of Steward has no mail account set up. "
    "You'll need to pass the word along yourself."
)

# RFC 2606 / RFC 6761 reserve these so they can never receive mail. The test
# scripts drive the real endpoint through TestClient, so without this guard every
# suite run submits an invite to a domain with no mail exchanger — Gmail accepts
# it, fails to deliver, and bounces a delivery-failure notice into the sending
# account's inbox. Skipping is both correct and quieter: there is no address here
# to reach.
UNDELIVERABLE_DOMAINS = (
    "example.com", "example.net", "example.org",
    ".test", ".invalid", ".example", ".localhost",
)


def is_undeliverable(email: str) -> bool:
    """True for reserved domains that by definition cannot receive mail."""
    domain = email.strip().rsplit("@", 1)[-1].lower()
    return domain in UNDELIVERABLE_DOMAINS or domain.endswith(
        tuple(d for d in UNDELIVERABLE_DOMAINS if d.startswith("."))
    )


def credentials() -> tuple[Optional[str], Optional[str]]:
    """The Gmail address and app password, or (None, None) if not configured."""
    load_env()
    address = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not address or not password:
        return None, None
    # Google shows app passwords in four spaced groups; people paste them that
    # way, and SMTP rejects the spaces.
    return address, password.replace(" ", "")


def _greeting(display_name: Optional[str]) -> str:
    name = (display_name or "").strip()
    return f"Hello {name}," if name else "Hello,"


def invite_text(
    display_name: Optional[str], estate_name: str, inviter_name: Optional[str], link: str
) -> str:
    """The email as plain words.

    Written the way one person writes to another about a death in the family:
    say who asked, say what it is, say there is no hurry. No "You have been
    invited to join a workspace", no button that shouts, nothing about
    activating an account.
    """
    asked_by = f"{inviter_name} has" if inviter_name else "The executor has"
    return f"""{_greeting(display_name)}

{asked_by} asked you to {estate_name} on Steward, where the family is going
through the house a piece at a time — a photograph of each thing, what it is,
and what sort of condition it's in.

You can look through all of it, and put your name to anything that matters to
you. If someone else asks for the same thing, that's alright; it just means the
two of you talk before anything is settled.

To get in, set yourself a password here:

{link}

That link is yours alone, and it will expire after a while — if it has gone
stale by the time you get to it, ask for a new one from the sign-in page.

There's no hurry on any of this. Nothing has to be decided today.

— Steward
"""


def invite_html(
    display_name: Optional[str], estate_name: str, inviter_name: Optional[str], link: str
) -> str:
    """The same words, set on cream. Restrained on purpose — an estate email
    that arrives looking like a marketing campaign is the wrong thing entirely.
    """
    asked_by = f"{inviter_name} has" if inviter_name else "The executor has"
    return f"""\
<div style="background:#fdf6f1;padding:32px 16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <div style="max-width:520px;margin:0 auto;background:#fffaf6;border:1px solid rgba(135,115,109,0.18);border-radius:18px;padding:32px 34px;">
    <p style="margin:0 0 22px;font-size:15px;color:#6b5a52;">{_greeting(display_name)}</p>
    <h1 style="margin:0 0 20px;font-family:Georgia,'Times New Roman',serif;font-size:26px;line-height:1.25;font-weight:600;color:#211a14;">
      {asked_by} asked you to {estate_name}.
    </h1>
    <p style="margin:0 0 16px;font-size:16px;line-height:1.65;color:#4a3e37;">
      The family is going through the house a piece at a time — a photograph of
      each thing, what it is, and what sort of condition it's in.
    </p>
    <p style="margin:0 0 16px;font-size:16px;line-height:1.65;color:#4a3e37;">
      You can look through all of it, and put your name to anything that matters
      to you. If someone else asks for the same thing, that's alright; it just
      means the two of you talk before anything is settled.
    </p>
    <p style="margin:26px 0;">
      <a href="{link}" style="display:inline-block;background:#8e4831;color:#fffaf6;text-decoration:none;font-size:16px;font-weight:600;padding:15px 26px;border-radius:999px;">
        Set a password
      </a>
    </p>
    <p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:#6b5a52;">
      That link is yours alone, and it will expire after a while — if it has gone
      stale by the time you get to it, ask for a new one from the sign-in page.
    </p>
    <p style="margin:0 0 22px;font-size:16px;line-height:1.65;color:#4a3e37;">
      There's no hurry on any of this. Nothing has to be decided today.
    </p>
    <p style="margin:0;padding-top:18px;border-top:1px solid rgba(135,115,109,0.18);font-size:14px;color:#6b5a52;">
      — Steward
    </p>
  </div>
</div>
"""


def send(
    to_email: str,
    subject: str,
    text: str,
    html: Optional[str] = None,
    kind: str = "email",
    failure_note: Optional[str] = None,
) -> SendResult:
    """Send one message. Never raises — the caller's work is already done.

    The one place SMTP is spoken in this codebase. Every outbound email goes
    through here so credentials, reserved-domain skipping, TLS and failure
    handling exist once rather than once per notification.
    """
    if is_undeliverable(to_email):
        logger.info("%s email skipped for %s: reserved domain", kind, to_email)
        return SendResult(
            False,
            f"No email went to {to_email} — that's a reserved test domain that "
            "can't receive mail.",
        )

    address, password = credentials()
    if address is None or password is None:
        logger.warning(
            "%s email skipped for %s: GMAIL_ADDRESS/GMAIL_APP_PASSWORD not set",
            kind, to_email,
        )
        return SendResult(False, NO_CREDENTIALS)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((FROM_NAME, address))
    message["To"] = to_email
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(address, password)
            smtp.send_message(message)
    except Exception as exc:  # noqa: BLE001 — every failure degrades the same way
        # The address is logged, the credentials never are.
        logger.exception("%s email to %s failed", kind, to_email)
        return SendResult(
            False,
            failure_note or f"That email didn't go out ({type(exc).__name__}).",
        )

    logger.info("%s email sent to %s", kind, to_email)
    return SendResult(True, f"An email is on its way to {to_email}.")


def send_invite_email(
    to_email: str,
    link: str,
    estate_name: str,
    display_name: Optional[str] = None,
    inviter_name: Optional[str] = None,
) -> SendResult:
    """Tell someone they've been asked to an estate. Never raises.

    Returns a SendResult either way. A caller that treats this as best-effort is
    correct: the membership already exists by the time this runs.
    """
    if is_undeliverable(to_email):
        logger.info(
            "invite email skipped for %s: reserved domain, cannot receive mail", to_email
        )
        return SendResult(
            False,
            f"No email went to {to_email} — that's a reserved test domain that "
            "can't receive mail.",
        )

    return send(
        to_email,
        subject=f"You've been asked to {estate_name}",
        text=invite_text(display_name, estate_name, inviter_name, link),
        html=invite_html(display_name, estate_name, inviter_name, link),
        kind="invite",
        failure_note=(
            "The invite is recorded, but the email didn't go out. "
            "Worth telling them yourself."
        ),
    )


