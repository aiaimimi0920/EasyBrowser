from .easy_email_client import Mailbox, create_mailbox, wait_openai_code
from .cloudflare_temp_email_client import (
    encode_direct_mailbox_ref,
    is_direct_mailbox_ref,
    wait_direct_mailbox_code,
)

__all__ = [
    "Mailbox",
    "create_mailbox",
    "wait_openai_code",
    "encode_direct_mailbox_ref",
    "is_direct_mailbox_ref",
    "wait_direct_mailbox_code",
]

