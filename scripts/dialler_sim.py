"""Stand in for the CRM dialler: post one recording to the ingestion endpoint.

    uv run python scripts/dialler_sim.py --lead L-1001 --file data/recordings/demo/call.wav

Posting the same file twice is the idempotency demo: the second post answers 200
with duplicate true and the same recording id.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest.dialler import sha256_of_file  # noqa: E402

DEFAULT_API = "http://127.0.0.1:8000"
CONTENT_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post a call recording as the dialler would.")
    parser.add_argument("--lead", required=True, help="lead_id the call belongs to")
    parser.add_argument("--file", required=True, type=Path, help="path to the audio file")
    parser.add_argument("--agent", default="A-001", help="agent id who took the call")
    parser.add_argument(
        "--started",
        default=None,
        help="call start as ISO 8601. Defaults to now in UTC.",
    )
    parser.add_argument("--api", default=DEFAULT_API, help=f"API base url, default {DEFAULT_API}")
    parser.add_argument("--timeout", type=float, default=60.0, help="request timeout in seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    audio_path: Path = args.file
    if not audio_path.is_file():
        print(f"No such file: {audio_path}")
        return 1

    started = args.started or datetime.now(UTC).isoformat()
    local_sha = sha256_of_file(audio_path)
    print(f"Posting {audio_path.name} ({audio_path.stat().st_size} bytes) for lead {args.lead}")
    print(f"  sha256 {local_sha}")

    content_type = CONTENT_TYPES.get(audio_path.suffix.lower(), "application/octet-stream")
    with audio_path.open("rb") as handle:
        files = {"audio": (audio_path.name, handle, content_type)}
        data = {"lead_id": args.lead, "call_started_at": started, "agent_id": args.agent}
        try:
            response = httpx.post(
                f"{args.api.rstrip('/')}/api/dialler/recordings",
                data=data,
                files=files,
                timeout=args.timeout,
            )
        except httpx.HTTPError as exc:
            print(f"Could not reach the API at {args.api}: {exc}")
            return 1

    if response.status_code not in (200, 202):
        print(f"Rejected with {response.status_code}: {response.text}")
        return 1

    body = response.json()
    where = "already stored" if body["duplicate"] else "stored"
    print(
        f"{response.status_code} {where} as recording {body['recording_id']}, "
        f"state {body['state']}"
    )
    if body["sha256"] != local_sha:
        print("  warning: server hash differs from the local hash")
    if body.get("duration_s") is not None:
        print(f"  {body['channels']} channel(s), {body['duration_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
