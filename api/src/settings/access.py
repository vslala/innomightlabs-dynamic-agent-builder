"""Who may change the account's settings and credentials: provider keys, OAuth connections, MCP connections, A2A,
dream and smart-suggestion settings. They belong to the account, like an organisation's: its admins connect them
(`settings:Manage`, in AdministratorAccess) and every member's agents use them. See
docs/LLD-shared-accounts-and-iam.md, "Account settings and credentials".
"""

from typing import Annotated

from fastapi import Depends

from src.iam.dependencies import get_principal
from src.iam.principal import Principal, load_principal
from src.iam.service import IamError

MANAGE_SETTINGS = "settings:Manage"


def settings_manager(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    """The caller, when they may change the account's settings; 403 otherwise."""
    principal.require(MANAGE_SETTINGS)
    return principal


def may_manage_settings(user_id: str, account_id: str) -> bool:
    """For flows that finish in a later request (OAuth callbacks): whether the person who started one may still
    change that account's settings."""
    try:
        return load_principal(user_id, account_id).can(MANAGE_SETTINGS).allowed
    except IamError:
        return False
