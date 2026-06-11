from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from autoresearch_api.programs.spec import ProgramSpec, parse_research_yaml

DEFAULT_API_URL = "http://127.0.0.1:8000"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crucible",
        description="Crucible research operating system CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser(
        "import",
        help="Validate a research.yaml spec and create the program via the API.",
    )
    import_parser.add_argument("spec", type=Path, help="Path to a research.yaml file.")
    import_parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Control-plane base URL (default: {DEFAULT_API_URL}).",
    )
    import_parser.set_defaults(handler=_cmd_import)

    args = parser.parse_args(argv)
    handler = args.handler
    return handler(args)


def _cmd_import(args: argparse.Namespace) -> int:
    try:
        spec = parse_research_yaml(args.spec.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"error: cannot read {args.spec}: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: invalid spec: {exc}", file=sys.stderr)
        return 2

    try:
        program = _post_program(args.api_url, spec)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(f"error: API returned {exc.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"error: could not reach API at {args.api_url}: {exc.reason}", file=sys.stderr)
        return 1

    print(f"created program {program['id']} ({program['name']}, type={program['type']})")
    return 0


def _post_program(api_url: str, spec: ProgramSpec) -> dict[str, object]:
    url = api_url.rstrip("/") + "/programs"
    body = json.dumps(spec.model_dump(mode="json")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
