from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sysml-spec", description="SysML v2 / KerML spec QA")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ingest = sub.add_parser("ingest", help="Download specs and build the SQLite index")
    ingest.add_argument("--version", default="2.0", choices=["2.0", "2.1", "all"])
    ingest.add_argument("--skip-download", action="store_true")

    sub.add_parser("serve", help="Run the localhost PDF viewer (127.0.0.1:8787)")
    sub.add_parser("mcp", help="Run the Cursor MCP server on stdio")
    sub.add_parser("eval", help="Run retrieval eval questions")

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        from .ingest.build import ingest as ingest_one
        from .ingest.build import ingest_all

        if args.version == "all":
            ingest_all(["2.0", "2.1"], skip_download=args.skip_download)
        else:
            ingest_one(args.version, skip_download=args.skip_download)
        return
    if args.cmd == "serve":
        from .viewer_app import main as serve

        serve()
        return
    if args.cmd == "mcp":
        from .mcp_server import main as mcp_main

        mcp_main()
        return
    if args.cmd == "eval":
        from .eval_run import main as eval_main

        raise SystemExit(eval_main())


if __name__ == "__main__":
    main(sys.argv[1:])
