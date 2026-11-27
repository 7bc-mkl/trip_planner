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
    #
    # CLIENT_IP_SOURCE=cloudfront (the Lambda target): no proxy headers. Behind a
    # Function URL, X-Forwarded-For is viewer-controlled, and --proxy-headers
    # would rewrite the client address from it; the Lambda Web Adapter connects
    # from 127.0.0.1, so there is no proxy here to trust anyway. Normalised the
    # way config.py reads it, so " CloudFront " cannot pick the app's rule while
    # leaving the proxy headers on.
    client_ip_source=$(printf '%s' "${CLIENT_IP_SOURCE:-}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
    if [ "$client_ip_source" = "cloudfront" ]; then
      exec uvicorn trip_planner.app:create_production_app \
        --factory \
        --host 0.0.0.0 \
        --port "${PORT:-8000}"
    fi
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
