"""Route protection, enforced by enumeration rather than by review vigilance.

R08 says nothing showing a plan is reachable without an owner session. The way
that requirement is normally broken is not by removing a check — it is by adding a
route and forgetting one. So this file walks every route the application actually
registers and asserts each is either on the public allow-list or carries the
session dependency.

The `/trips/…` assertions are deliberately written before the trip routes exist
(they arrive in Phase 2). They are vacuous today and become load-bearing the
moment the first trip route is registered, which is the point: the guard is in
place *before* the routes it protects, not added afterwards.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from trip_planner.api.deps import get_current_owner, get_current_session
from trip_planner.app import API_PREFIX, PUBLIC_PATHS, create_app

#: FastAPI's own machinery, not application surface.
INFRASTRUCTURE_PATHS = frozenset({"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"})


@dataclass(frozen=True)
class RouteInfo:
    """One registered route, with its dependencies fully resolved."""

    path: str
    methods: frozenset[str]
    dependencies: frozenset[object]

    def __str__(self) -> str:
        return f"{sorted(self.methods)} {self.path}"


def _resolve(dependant: object) -> set[object]:
    """Every dependency reachable from a dependant, including nested ones.

    Walking the tree matters: `get_current_owner` depends on `get_current_session`,
    so a route that only names the former is still protected, and a check that only
    looked at the top level would report a false failure.
    """
    seen: set[object] = set()
    stack = list(dependant.dependencies)  # type: ignore[attr-defined]

    while stack:
        dependency = stack.pop()
        if dependency.call is not None:
            seen.add(dependency.call)
        stack.extend(dependency.dependencies)

    return seen


def api_routes(app: FastAPI) -> Iterator[RouteInfo]:
    """Every route the application actually serves, with router prefixes applied.

    `include_router` wraps its routes rather than flattening them onto
    `app.routes`, and router-level dependencies are attached at that wrapper. So
    the enumeration goes through the resolved route contexts, not the raw list —
    reading `app.routes` alone would see no application routes at all and every
    assertion below would pass vacuously.
    """
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            for context in contexts():
                if context.path not in INFRASTRUCTURE_PATHS:
                    yield RouteInfo(
                        path=context.path,
                        methods=frozenset(context.methods or ()),
                        dependencies=frozenset(_resolve(context.dependant)),
                    )
        elif isinstance(route, APIRoute) and route.path not in INFRASTRUCTURE_PATHS:
            yield RouteInfo(
                path=route.path,
                methods=frozenset(route.methods or ()),
                dependencies=frozenset(_resolve(route.dependant)),
            )


def dependency_callables(route: RouteInfo) -> frozenset[object]:
    return route.dependencies


@pytest.fixture(scope="module")
def application() -> FastAPI:
    return create_app()


def test_the_application_registers_routes(application: FastAPI) -> None:
    """Guards the file itself: an empty enumeration would pass everything below."""
    assert list(api_routes(application))


def test_every_route_is_public_by_declaration_or_authenticated(application: FastAPI) -> None:
    unprotected: list[str] = []

    for route in api_routes(application):
        if route.path in PUBLIC_PATHS:
            continue
        if get_current_session not in dependency_callables(route):
            unprotected.append(str(route))

    assert unprotected == [], (
        "These routes are neither on PUBLIC_PATHS nor authenticated: "
        f"{unprotected}. Add the session dependency, or add the path to "
        "PUBLIC_PATHS in trip_planner/app.py if it is genuinely public."
    )


def test_the_public_allow_list_has_no_stale_entries(application: FastAPI) -> None:
    """A path left on the allow-list after its route moved is a hole nobody sees."""
    registered = {route.path for route in api_routes(application)}
    stale = sorted(PUBLIC_PATHS - registered)

    assert stale == [], f"PUBLIC_PATHS names paths no route serves: {stale}"


def test_the_public_allow_list_stays_small(application: FastAPI) -> None:
    """Every public path is a decision. This fails when one is added silently."""
    assert frozenset(
        {
            f"{API_PREFIX}/health",
            f"{API_PREFIX}/auth/login",
            f"{API_PREFIX}/auth/logout",
        }
    ) == PUBLIC_PATHS


def test_every_trip_scoped_route_resolves_ownership_through_the_shared_dependency(
    application: FastAPI,
) -> None:
    """URL nesting enforces nothing; the dependency is the enforcement.

    A handler that joins to the trip by hand can forget the owner clause, and the
    resulting endpoint happily serves another owner's data. Vacuous until Phase 2
    registers the first `/trips/…` route.
    """
    try:
        from trip_planner.api.deps import get_owned_trip
    except ImportError:
        get_owned_trip = None

    offenders: list[str] = []

    for route in api_routes(application):
        if not route.path.startswith(f"{API_PREFIX}/trips"):
            continue
        if get_owned_trip is None or get_owned_trip not in dependency_callables(route):
            offenders.append(str(route))

    assert offenders == [], (
        "These trip-scoped routes do not take get_owned_trip: "
        f"{offenders}. Ownership must be resolved by the shared dependency so no "
        "handler can forget the owner clause."
    )


def test_get_current_owner_implies_get_current_session(application: FastAPI) -> None:
    """The nesting the enumeration above relies on."""
    for route in api_routes(application):
        dependencies = dependency_callables(route)
        if get_current_owner in dependencies:
            assert get_current_session in dependencies, route.path
