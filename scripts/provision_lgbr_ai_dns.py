"""Create proxied CNAMEs for universe/shape/mcp on lgbr-ai.com.

Uses ~/.cloudflared/cert.pem (must be the lgbr-ai.com account login).
Target tunnel: lgbr-ai (71ec1071-7bce-4e3c-b43f-53fafc55bb3e).
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

TUNNEL_ID = "71ec1071-7bce-4e3c-b43f-53fafc55bb3e"
HOSTS = (
    "universe.lgbr-ai.com",
    "shape.lgbr-ai.com",
    "mcp.lgbr-ai.com",
)


def _cred() -> dict:
    lines = Path.home().joinpath(".cloudflared/cert.pem").read_text().splitlines()
    body = "".join(l for l in lines if not l.startswith("-----"))
    raw = base64.b64decode(body + "=" * ((4 - len(body) % 4) % 4))
    return json.loads(raw)


def api(token: str, method: str, path: str, body: dict | None = None) -> dict:
    cmd = [
        "/usr/bin/curl",
        "-sS",
        "-X",
        method,
        f"https://api.cloudflare.com/client/v4{path}",
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        "Content-Type: application/json",
    ]
    if body is not None:
        cmd += ["-d", json.dumps(body)]
    return json.loads(subprocess.check_output(cmd))


def main() -> None:
    cred = _cred()
    token = cred["apiToken"]
    zone_id = cred.get("zoneID")
    zones = api(token, "GET", "/zones?name=lgbr-ai.com")
    if not zones.get("success"):
        print("zone lookup failed:", zones.get("errors"), file=sys.stderr)
        raise SystemExit(1)
    results = zones.get("result") or []
    if not results:
        print(
            "lgbr-ai.com not visible to ~/.cloudflared/cert.pem.\n"
            "Run: cloudflared tunnel login  (select lgbr-ai.com)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    zid = zone_id or results[0]["id"]
    target = f"{TUNNEL_ID}.cfargotunnel.com"
    for host in HOSTS:
        existing = api(token, "GET", f"/zones/{zid}/dns_records?name={host}").get("result") or []
        body = {
            "type": "CNAME",
            "name": host,
            "content": target,
            "ttl": 1,
            "proxied": True,
        }
        if existing:
            r = api(token, "PUT", f"/zones/{zid}/dns_records/{existing[0]['id']}", body)
            action = "update"
        else:
            r = api(token, "POST", f"/zones/{zid}/dns_records", body)
            action = "create"
        if not r.get("success"):
            print(action, host, "FAILED", r.get("errors"), file=sys.stderr)
            raise SystemExit(1)
        print(action, host, "->", target)
    print("OK")


if __name__ == "__main__":
    main()
