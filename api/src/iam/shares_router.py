"""Share routes on every shareable type: `/{collection}/{id}/shares[/{members|groups}/{id}]`.

Literal paths per type rather than one `/{collection}/...` route, so they never shadow a resource's own
routes.
"""

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, Response, status

from .dependencies import get_principal
from .principal import Principal
from .schemas import ShareRequest, ShareResponse
from .shares import ResourceShare, ShareService

COLLECTIONS = {"agents": "agent", "knowledge-bases": "knowledge-base", "automations": "automation", "kits": "kit"}

router = APIRouter(tags=["shares"])


def _response(share: ResourceShare) -> ShareResponse:
    return ShareResponse(**{**asdict(share), "actions": list(share.actions)})


def _routes(collection: str, resource_type: str) -> None:
    base = f"/{collection}/{{resource_id}}/shares"

    @router.get(base, response_model=list[ShareResponse], name=f"list_{resource_type}_shares")
    async def list_shares(resource_id: str, principal: Principal = Depends(get_principal)) -> list[ShareResponse]:
        service = ShareService()
        resource = service.resolve(principal.account_id, resource_type, resource_id)
        return [_response(share) for share in service.who_has_access(principal.account_id, principal.user_id, resource)]

    @router.put(base + "/{grantee_kind}/{grantee_id}", response_model=ShareResponse,
                name=f"share_{resource_type}")
    async def share(resource_id: str, grantee_kind: Literal["members", "groups"], grantee_id: str,
                    body: ShareRequest, principal: Principal = Depends(get_principal)) -> ShareResponse:
        service = ShareService()
        resource = service.resolve(principal.account_id, resource_type, resource_id)
        return _response(service.share(principal.account_id, principal.user_id, resource,
                                       "member" if grantee_kind == "members" else "group", grantee_id,
                                       preset=body.preset, actions=body.actions))

    @router.delete(base + "/{grantee_kind}/{grantee_id}", status_code=status.HTTP_204_NO_CONTENT,
                   name=f"revoke_{resource_type}_share")
    async def revoke(resource_id: str, grantee_kind: Literal["members", "groups"], grantee_id: str,
                     principal: Principal = Depends(get_principal)) -> Response:
        service = ShareService()
        resource = service.resolve(principal.account_id, resource_type, resource_id)
        service.revoke(principal.account_id, principal.user_id, resource,
                       "member" if grantee_kind == "members" else "group", grantee_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


for _collection, _resource_type in COLLECTIONS.items():
    _routes(_collection, _resource_type)
