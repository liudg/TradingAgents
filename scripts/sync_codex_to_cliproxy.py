import argparse
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error
from urllib import parse, request


OPENAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"
EXIT_NO_CHANGES = 10


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


def parse_token_expiry(token: str) -> datetime | None:
    claims = decode_jwt_payload(token)
    exp = claims.get("exp")
    if exp is None:
        return None
    return datetime.fromtimestamp(int(exp), tz=timezone.utc)


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
    try:
        with opener.open(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        message = f"Failed to refresh Codex tokens: HTTP {exc.code} {exc.reason}"
        if details:
            message = f"{message}; response={details}"
        raise RuntimeError(message) from exc


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


def build_cliproxy_auth(tokens: dict, now: datetime) -> tuple[dict, str]:
    id_claims = decode_jwt_payload(tokens["id_token"])
    auth_info = id_claims.get("https://api.openai.com/auth", {})
    email = id_claims["email"]
    account_id = tokens.get("account_id") or auth_info.get("chatgpt_account_id", "")
    plan_type = auth_info.get("chatgpt_plan_type", "")

    access_expires_at = parse_token_expiry(tokens["access_token"])
    if access_expires_at is None:
        expires_at = now + timedelta(seconds=int(tokens.get("expires_in", 0)))
    else:
        expires_at = access_expires_at

    output = {
        "id_token": tokens["id_token"],
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "account_id": account_id,
        "last_refresh": format_ts(now),
        "email": email,
        "type": "codex",
        "expired": format_ts(expires_at),
    }
    return output, plan_type


def auth_payload_changed(existing: dict, desired: dict) -> bool:
    keys = (
        "id_token",
        "access_token",
        "refresh_token",
        "account_id",
        "email",
        "type",
        "expired",
    )
    return any(existing.get(key) != desired.get(key) for key in keys)


def main() -> int:
    args = parse_args()

    codex_auth_path = Path(args.codex_auth)
    cliproxy_auth_dir = Path(args.cliproxy_auth_dir)

    if not codex_auth_path.exists():
        raise FileNotFoundError(f"Codex auth file not found: {codex_auth_path}")

    local_auth = read_json(codex_auth_path)
    now = datetime.now(timezone.utc)
    local_tokens = local_auth["tokens"]
    access_expires_at = parse_token_expiry(local_tokens["access_token"])

    token_source = "refreshed"
    if access_expires_at and access_expires_at > now:
        tokens = local_tokens
        token_source = "cached"
    else:
        refresh_token = local_tokens["refresh_token"]
        try:
            tokens = refresh_codex_tokens(refresh_token, args.proxy)
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc}\nLocal cached access token is also expired. "
                "Please run `codex login` and retry."
            ) from exc

    output, plan_type = build_cliproxy_auth(tokens, now)
    email = output["email"]

    cliproxy_auth_dir.mkdir(parents=True, exist_ok=True)
    output_path = cliproxy_auth_dir / build_output_filename(email, plan_type)
    if output_path.exists():
        existing_output = read_json(output_path)
        if not auth_payload_changed(existing_output, output):
            print(f"CLIProxyAPI auth is already up to date: {output_path}")
            print(f"Token source: {token_source}")
            print(f"Email: {email}")
            print(f"Plan: {plan_type or 'unknown'}")
            print(f"Expires: {output['expired']}")
            return EXIT_NO_CHANGES

    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote CLIProxyAPI Codex auth file: {output_path}")
    print(f"Token source: {token_source}")
    print(f"Email: {email}")
    print(f"Plan: {plan_type or 'unknown'}")
    print(f"Expires: {output['expired']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
