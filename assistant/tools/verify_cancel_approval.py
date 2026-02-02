import argparse
import json
from urllib import request, parse, error


def _post(url, data=None):
    headers = {"Content-Type": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
    except Exception as e:
        return f"ERROR: {e}"


def main():
    parser = argparse.ArgumentParser(description="Verify cancel/approval flows")
    parser.add_argument("--base", default="http://127.0.0.1:8400", help="Base URL")
    parser.add_argument("--session", type=int, required=True, help="session_id")
    parser.add_argument("--run-id", default="", help="run_id (required for approval)")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    session_id = args.session

    print("Cancel endpoint test...")
    cancel_url = f"{base}/api/v1/agent/cancel?session_id={session_id}"
    print(_post(cancel_url))

    if args.run_id:
        print("Approval endpoint test...")
        approval_url = f"{base}/api/v1/agent/{session_id}/approval?run_id={parse.quote(args.run_id)}"
        print(_post(approval_url, {"approved": True, "feedback": ""}))
        quick_url = f"{base}/api/v1/approve/{session_id}?run_id={parse.quote(args.run_id)}"
        print(_post(quick_url))
    else:
        print("Skipping approval test (no --run-id provided)")


if __name__ == "__main__":
    main()
