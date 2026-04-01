"""Manus API 处理器：读取原始热点 → 调用 Manus 四层漏斗 → 写入 result.md"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

import httpx

import yaml

logger = logging.getLogger(__name__)


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "sources.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _build_markdown(items: list[dict], run_date: str) -> str:
    """将热点 items 转为精简 Markdown，用于文件附件上传。

    URL 直接绑在来源名上（markdown link 格式），
    这样 Manus 在四层漏斗中引用信源时能自然保留链接。
    """
    lines = [f"# 原始热点 {run_date}", "", f"共 {len(items)} 条", ""]
    for it in items:
        source = it.get("source", "")
        title = it.get("title", "")
        content = it.get("content", "")[:200]
        url = it.get("url", "")
        # 把 URL 绑在来源名上，漏斗过程中自然跟着走
        source_ref = f"[{source}]({url})" if url else source
        lines.append(f"## {title}")
        lines.append(f"- 来源: {source_ref}")
        lines.append(f"- 摘要: {content}")
        lines.append("")
    return "\n".join(lines)


def _build_prompt(run_date: str, item_count: int) -> str:
    return f"""今日任务

运行日期：{run_date}
原始热点条数：{item_count}

附件中是今日从 RSS、Twitter、Telegram 抓取的原始热点列表（Markdown 格式）。
请按四层漏斗完整处理，输出最终行动包。"""


async def _upload_file(client: httpx.AsyncClient, api_key: str, base_url: str, filename: str, content_bytes: bytes) -> str:
    """两步上传文件到 Manus：创建文件记录 → PUT 上传内容。"""
    resp = await client.post(
        f"{base_url}/files",
        headers={"API_KEY": api_key, "Content-Type": "application/json"},
        json={"filename": filename},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    file_id = data["id"]
    upload_url = data["upload_url"]

    await client.put(
        upload_url,
        content=content_bytes,
        timeout=60.0,
    )
    logger.info(f"[Manus] File uploaded: {filename} (id={file_id})")
    return file_id


async def _create_task(client: httpx.AsyncClient, prompt: str, api_key: str, project_id: str, base_url: str, file_id: str | None = None) -> str:
    body = {
        "prompt": prompt,
        "projectId": project_id,
        "locale": "zh-CN",
    }
    if file_id:
        body["attachments"] = [{"file_id": file_id}]
    resp = await client.post(
        f"{base_url}/tasks",
        headers={"API_KEY": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    task_id = data.get("task_id") or data.get("id")
    if not task_id:
        raise ValueError(f"No task_id in response: {data}")
    logger.info(f"[Manus] Task created: {task_id}")
    return task_id


async def _poll_task(client: httpx.AsyncClient, task_id: str, api_key: str, base_url: str, poll_interval: int, timeout: int) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(poll_interval)
        resp = await client.get(
            f"{base_url}/tasks/{task_id}",
            headers={"API_KEY": api_key},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "")
        logger.info(f"[Manus] Task {task_id} status: {status}")

        if status == "completed":
            return data
        elif status == "failed":
            raise RuntimeError(f"Manus task failed: {data.get('error', 'unknown')}")

    raise TimeoutError(f"Manus task {task_id} timed out after {timeout}s")


def _extract_output(task_data: dict) -> str:
    """从 Manus task 输出中提取文本内容。"""
    parts: list[str] = []

    for output in task_data.get("output", []):
        for content in output.get("content", []):
            # 文本输出
            if content.get("type") == "output_text":
                text = content.get("text", "").strip()
                if text:
                    parts.append(text)
            # 文件附件（下载文本类文件）
            elif content.get("fileUrl") and content.get("mimeType", "").startswith("text"):
                try:
                    resp = httpx.get(content["fileUrl"], timeout=30.0)
                    resp.raise_for_status()
                    parts.append(resp.text.strip())
                except Exception:
                    pass

    if not parts:
        raise ValueError("No output text found in Manus response")

    return "\n\n".join(parts)


async def process(raw_path: Path, output_path: Path, run_date: str) -> str:
    api_key = os.environ.get("MANUS_API_KEY", "")
    if not api_key:
        raise EnvironmentError("MANUS_API_KEY not set")
    project_id = os.environ.get("MANUS_PROJECT_ID", "")
    if not project_id:
        raise EnvironmentError("MANUS_PROJECT_ID not set")
    base_url = "https://api.manus.ai/v1"

    cfg = _load_config()
    poll_interval = cfg.get("manus_poll_interval", 60)
    timeout = cfg.get("manus_timeout", 1800)

    if not raw_path.exists():
        raise FileNotFoundError(f"Raw items not found: {raw_path}")

    with open(raw_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    logger.info(f"[Manus] Processing {len(items)} items for {run_date}")

    md_content = _build_markdown(items, run_date)
    logger.info(f"[Manus] Markdown size: {len(md_content)} chars, {len(items)} items")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        file_id = await _upload_file(client, api_key, base_url, f"hotspots_{run_date}.md", md_content.encode("utf-8"))
        prompt = _build_prompt(run_date, len(items))
        task_id = await _create_task(client, prompt, api_key, project_id, base_url, file_id)
        task_data = await _poll_task(client, task_id, api_key, base_url, poll_interval, timeout)

    result = _extract_output(task_data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)

    logger.info(f"[Manus] Result written to {output_path}")

    # 生成 result.json 供看板使用
    from processor.extractor import extract
    json_path = output_path.parent / "result.json"
    try:
        parsed = await extract(result, run_date)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
        logger.info(f"[Manus] Parsed JSON written to {json_path}")
    except Exception as e:
        logger.warning(f"[Manus] Parse failed: {e}")

    return result
