import argparse
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import parse, request


OPENAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh local Codex CLI tokens and write a CLIProxyAPI auth file."
    )
    parser.add_argument(
        "--codex-auth",
        default=str(Path.home() / ".codex" / "auth.json"),
        help="Path to the local Codex auth.json file.",
    )
    parser.add_argument(
        "--cliproxy-auth-dir",
        default=str(Path.home() / ".cli-proxy-api"),
        help="CLIProxyAPI auth directory.",
    )
    parser.add_argument(
        "--proxy",
        default=(
            os.getenv("HTTPS_PROXY")
            or os.getenv("https_proxy")
            or os.getenv("ALL_PROXY")
            or os.getenv("all_proxy")
            or os.getenv("HTTP_PROXY")
            or os.getenv("http_proxy")
        ),
        help="Optional HTTP/HTTPS proxy URL.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT token format.")

    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def build_opener(proxy_url: str | None):
    if proxy_url:
        return request.build_opener(
            request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
    return request.build_opener()


def refresh_codex_tokens(refresh_token: str, proxy_url: str | None) -> dict:
    body = parse.urlencode(
        {
            "client_id": OPENAI_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "openid profile email",
        }
    ).encode()
    req = request.Request(
        OPENAI_TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    opener = build_opener(proxy_url)
    with opener.open(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def format_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_output_filename(email: str, plan_type: str) -> str:
    normalized_plan = "-".join(
        part.lower()
        for part in "".join(ch if ch.isalnum() else " " for ch in plan_type).split()
    )
    if normalized_plan:
        return f"codex-{email}-{normalized_plan}.json"
    return f"codex-{email}.json"


def main() -> int:
    args = parse_args()

    codex_auth_path = Path(args.codex_auth)
    cliproxy_auth_dir = Path(args.cliproxy_auth_dir)

    if not codex_auth_path.exists():
        raise FileNotFoundError(f"Codex auth file not found: {codex_auth_path}")

    local_auth = read_json(codex_auth_path)
    refresh_token = local_auth["tokens"]["refresh_token"]
    refreshed = refresh_codex_tokens(refresh_token, args.proxy)

    claims = decode_jwt_payload(refreshed["id_token"])
    auth_info = claims.get("https://api.openai.com/auth", {})
    email = claims["email"]
    account_id = auth_info.get("chatgpt_account_id", "")
    plan_type = auth_info.get("chatgpt_plan_type", "")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=int(refreshed.get("expires_in", 0)))

    output = {
        "id_token": refreshed["id_token"],
        "access_token": refreshed["access_token"],
        "refresh_token": refreshed["refresh_token"],
        "account_id": account_id,
        "last_refresh": format_ts(now),
        "email": email,
        "type": "codex",
        "expired": format_ts(expires_at),
    }

    cliproxy_auth_dir.mkdir(parents=True, exist_ok=True)
    output_path = cliproxy_auth_dir / build_output_filename(email, plan_type)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote CLIProxyAPI Codex auth file: {output_path}")
    print(f"Email: {email}")
    print(f"Plan: {plan_type or 'unknown'}")
    print(f"Expires: {output['expired']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
