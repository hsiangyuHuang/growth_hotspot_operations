"""Vercel Serverless: POST /api/tracking/accept — 采纳/取消采纳"""
import json
import os
import base64
from http.server import BaseHTTPRequestHandler
import urllib.request

REPO = "hsiangyuHuang/osl_growth_hotspot_agent"


def _gh_api(path, method="GET", data=None):
    """调用 GitHub API"""
    token = os.environ.get("GITHUB_TOKEN", "")
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "osl-tracking",
    }
    if data:
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _read_tracking(date_str):
    """从 GitHub 读取 tracking 文件，返回 (data, sha)"""
    path = f"data/tracking/{date_str}/status.json"
    result = _gh_api(path)
    if result and "content" in result:
        content = base64.b64decode(result["content"]).decode()
        return json.loads(content), result["sha"]
    return {"run_date": date_str, "cards": {}}, None


def _write_tracking(date_str, data, sha):
    """写入 tracking 文件到 GitHub"""
    path = f"data/tracking/{date_str}/status.json"
    content = json.dumps(data, ensure_ascii=False, indent=2)
    payload = {
        "message": f"tracking: update {date_str}",
        "content": base64.b64encode(content.encode()).decode(),
    }
    if sha:
        payload["sha"] = sha
    _gh_api(path, method="PUT", data=payload)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        date_str = body.get("date")
        card_id = body.get("card_id")
        channel = body.get("channel")
        browser_id = body.get("browser_id")

        if not all([date_str, card_id, channel, browser_id]):
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"date, card_id, channel, browser_id required"}')
            return

        # 读取 → 修改 → 写回
        data, sha = _read_tracking(date_str)
        card_data = data["cards"].setdefault(card_id, {})
        ids = card_data.get(channel, [])
        if browser_id in ids:
            ids.remove(browser_id)
            accepted = False
        else:
            ids.append(browser_id)
            accepted = True
        card_data[channel] = ids
        _write_tracking(date_str, data, sha)

        resp = json.dumps({"ok": True, "count": len(ids), "accepted": accepted})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(resp.encode())
