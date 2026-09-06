#!/bin/sh
# Container entrypoint.
#
# `migrate` is the release step and `serve` takes traffic. They are separate
# commands on purpose: the spec requires `alembic upgrade head` to run BEFORE the
# new image starts serving, and a platform that runs a release command needs
# something to point at. Where no such hook exists, `migrate-and-serve` does both
# in order — correct for the single instance this milestone deploys, and the
# thing to stop using the day a second replica appears, since every replica would
# then race to migrate.
set -eu

case "${1:-serve}" in
  migrate)
    exec alembic upgrade head
    ;;

  serve)
    # --factory: the app is built by a function that validates configuration
    # first, so a missing variable is a startup crash naming it rather than a
    # confusing failure on the first request.
    exec uvicorn trip_planner.app:create_production_app \
      --factory \
      --host 0.0.0.0 \
      --port "${PORT:-8000}" \
      --proxy-headers \
      --forwarded-allow-ips '*'
    ;;

  migrate-and-serve)
    alembic upgrade head
    exec "$0" serve
    ;;

  *)
    exec "$@"
    ;;
esac
