"""Liveness endpoint.

Deliberately unauthenticated: a load balancer has no session, and the response
carries no information about the plan behind the login.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str


@router.get("/health")
def health() -> Health:
    return Health(status="ok")
