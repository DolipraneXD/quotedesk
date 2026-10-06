"""Run QuoteDesk: ``python -m app [--open] [--reload]`` from the backend folder."""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from app.config import FROZEN, HOST, PORT, data_dir


def main() -> None:
    parser = argparse.ArgumentParser(prog="quotedesk")
    parser.add_argument("--open", action="store_true", help="open the browser once started")
    parser.add_argument("--reload", action="store_true", help="auto-reload (development)")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    if FROZEN:  # double-clicked: open the browser, and say how to stop
        args.open, args.reload = True, False
        print(f"QuoteDesk is running on http://{HOST}:{args.port}")
        print(f"Data folder: {data_dir()}")
        print("Close this window to stop QuoteDesk.")

    if args.open:
        url = f"http://{HOST}:{args.port}"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    # HOST is fixed to 127.0.0.1: there is no login, so the app must stay local.
    if args.reload:
        uvicorn.run("app.main:app", host=HOST, port=args.port, reload=True)
    else:
        from app.main import app  # a direct import also works in the frozen build

        uvicorn.run(app, host=HOST, port=args.port)


if __name__ == "__main__":
    main()
