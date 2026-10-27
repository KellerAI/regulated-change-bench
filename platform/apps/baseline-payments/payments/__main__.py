"""Run the service locally: python -m payments [--host 127.0.0.1] [--port 8080]."""

import argparse
from wsgiref.simple_server import make_server

from .app import LedgerApp
from .clock import SystemClock
from .service import build_service
from .session import SessionStore
from .transports import UrllibTransport


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="payments", description="Payments payment disbursement service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--database", default=":memory:")
    args = parser.parse_args(argv)
    clock = SystemClock()
    service = build_service(clock, UrllibTransport(), database=args.database)
    app = LedgerApp(service, SessionStore(clock), clock)
    with make_server(args.host, args.port, app) as server:
        print(f"payments listening on http://{args.host}:{args.port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
