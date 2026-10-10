from fastapi import Request

from .principal import Principal, load_principal
from .service import IamError

ACCOUNT_HEADER = "X-Account-Id"


def get_principal(request: Request) -> Principal:
    """The caller acting in the account named by `X-Account-Id`.

    KAN-79 moves this into the auth middleware, with the fallbacks (the last account used, then the
    oldest membership) for requests that don't name one.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise IamError(401, "NOT_AUTHENTICATED", "Not authenticated")
    account_id = request.headers.get(ACCOUNT_HEADER)
    if not account_id:
        raise IamError(400, "ACCOUNT_REQUIRED", f"Name the account in the {ACCOUNT_HEADER} header")
    return load_principal(str(user_id), account_id)
