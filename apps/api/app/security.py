"""Simple role-header authorization for the demonstrator.

This intentionally models authorization, not authentication. A production deployment
would place an OIDC/JWT authenticator in front of the same role dependencies.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from .schemas import Principal, Role

ROLE_LEVEL = {Role.reviewer: 10, Role.operator: 20, Role.admin: 30}


def require_role(minimum_role: Role) -> Callable[..., Principal]:
    def dependency(
        x_role: Annotated[str | None, Header(alias="X-Role")] = None,
        x_actor: Annotated[str | None, Header(alias="X-Actor")] = None,
    ) -> Principal:
        if not x_role:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "missing_role",
                    "message": "X-Role header is required for this operation",
                },
            )
        try:
            role = Role(x_role.strip().lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "invalid_role",
                    "message": "X-Role must be reviewer, operator, or admin",
                },
            ) from exc
        if ROLE_LEVEL[role] < ROLE_LEVEL[minimum_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "insufficient_role",
                    "message": f"This operation requires {minimum_role.value} or higher",
                },
            )
        return Principal(actor=(x_actor or f"demo-{role.value}").strip(), role=role)

    return dependency


ReviewerPrincipal = Annotated[Principal, Depends(require_role(Role.reviewer))]
OperatorPrincipal = Annotated[Principal, Depends(require_role(Role.operator))]
AdminPrincipal = Annotated[Principal, Depends(require_role(Role.admin))]
