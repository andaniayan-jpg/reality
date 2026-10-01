"""Public entry point for Reality's fixed-operation local bridge.

Run ``python -m reality.bridge --allow-root PATH`` to serve JSON Lines on
standard input/output. The bridge is intentionally not a Python shell.
"""

from ._bridge import BridgeRequestError, RealityBridge, main, serve_jsonl

__all__ = ["BridgeRequestError", "RealityBridge", "main", "serve_jsonl"]


if __name__ == "__main__":
    main()
