"""Vercel Serverless: GET /api/tracking?date=YYYY-MM-DD — 读取采纳数据"""
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request

REPO = "hsiangyuHuang/growth_hotspot_operations"


def _github_read(date_str):
    """从 GitHub 仓库读取 tracking 文件（无需 token，公开仓库直接读）"""
    url = f"https://raw.githubusercontent.com/{REPO}/main/data/tracking/{date_str}/status.json"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {"run_date": date_str, "cards": {}}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        date_str = qs.get("date", [""])[0]
        if not date_str:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"date parameter required"}')
            return

        data = _github_read(date_str)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
