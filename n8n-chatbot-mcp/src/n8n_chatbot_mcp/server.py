#!/usr/bin/env python3
"""
n8n Chatbot MCP Server
Generic MCP server for any n8n Chat Trigger webhook.

Auto-discovers chatbot name, description, and required headers from the
n8n Chat Trigger HTML page.

Environment variables:
    N8N_CHATBOT_URL         (required) Full webhook URL, e.g. https://n8n.example.com/webhook/my-bot/chat
    N8N_CHATBOT_DESCRIPTION (optional) Extra context appended to auto-discovered description
    N8N_CHATBOT_TIMEOUT     (optional) Request timeout in seconds (default: 120)
"""

import json
import os
import re
import sys
import uuid
import httpx
from mcp.server.fastmcp import FastMCP

CHATBOT_URL = os.environ.get("N8N_CHATBOT_URL", "")
CHATBOT_TIMEOUT = int(os.environ.get("N8N_CHATBOT_TIMEOUT", "120"))

if not CHATBOT_URL:
    print(
        "HATA: N8N_CHATBOT_URL environment variable zorunludur.\n"
        "Örnek: N8N_CHATBOT_URL=https://n8n.example.com/webhook/my-bot/chat",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Auto-discover chatbot config from n8n Chat Trigger HTML
# ---------------------------------------------------------------------------

def _discover_chat_config() -> dict:
    """GET the chat UI HTML and extract instance headers, name, description."""
    config: dict = {"headers": {}, "name": "", "description": "", "initial_messages": []}
    try:
        with httpx.Client(timeout=15, verify=False) as client:
            resp = client.get(CHATBOT_URL)
            if resp.status_code != 200 or "text/html" not in resp.headers.get("content-type", ""):
                return config
            html = resp.text

            # X-Instance-Id
            m = re.search(r"['\"]X-Instance-Id['\"]\s*:\s*['\"]([^'\"]+)['\"]", html)
            if m:
                config["headers"]["X-Instance-Id"] = m.group(1)

            # i18n title & subtitle  (e.g. en: {"subtitle":"...","title":"..."})
            m = re.search(r"i18n:\s*\{[^}]*?(\{[^}]+\})", html)
            if m:
                try:
                    i18n = json.loads(m.group(1))
                    config["name"] = i18n.get("title", "").strip()
                    config["description"] = i18n.get("subtitle", "").strip()
                except json.JSONDecodeError:
                    pass

            # initialMessages
            m = re.search(r"initialMessages:\s*(\[[^\]]+\])", html)
            if m:
                try:
                    config["initial_messages"] = json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return config


# Run discovery once at startup
_chat_config = _discover_chat_config()

_CHATBOT_NAME = _chat_config["name"] or "n8n Chatbot"
_REQUEST_HEADERS = _chat_config["headers"]

# Description: auto-discovered + env var (additive)
_desc_parts: list[str] = []
if _chat_config["description"]:
    _desc_parts.append(_chat_config["description"])
_extra_desc = os.environ.get("N8N_CHATBOT_DESCRIPTION", "")
if _extra_desc:
    _desc_parts.append(_extra_desc)
if _chat_config["initial_messages"]:
    _desc_parts.append(f"Karşılama: {_chat_config['initial_messages'][0]}")

mcp = FastMCP("n8n-chatbot")

# Shared HTTP client for parallel requests
_http_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(timeout=CHATBOT_TIMEOUT, verify=False)
    return _http_client


TOOL_DESCRIPTION = f"{_CHATBOT_NAME} chatbot'una soru sorar ve cevabını döner."
if _desc_parts:
    TOOL_DESCRIPTION += "\n" + "\n".join(_desc_parts)


@mcp.tool(description=TOOL_DESCRIPTION)
def ask_chatbot(question: str, session_id: str = "") -> str:
    """
    Args:
        question: Chatbot'a sorulacak soru
        session_id: Opsiyonel oturum ID'si (çoklu turlu konuşmalar için, boş bırakılırsa otomatik üretilir)

    Returns:
        Chatbot'un cevabı
    """
    payload = {
        "action": "sendMessage",
        "chatInput": question,
        "sessionId": session_id or str(uuid.uuid4()),
    }

    try:
        response = _get_client().post(CHATBOT_URL, json=payload, headers=_REQUEST_HEADERS)
        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict):
            return data.get("output") or data.get("text") or data.get("response") or str(data)
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                return first.get("output") or first.get("text") or str(first)
            return str(first)
        return str(data)

    except httpx.TimeoutException:
        return f"Hata: Chatbot {CHATBOT_TIMEOUT} saniye içinde yanıt vermedi."
    except httpx.HTTPStatusError as e:
        return f"Hata: Chatbot HTTP {e.response.status_code} hatası döndü."
    except httpx.ConnectError:
        return "Hata: Chatbot sunucusuna bağlanılamadı."
    except Exception as e:
        return f"Hata: {type(e).__name__}: {e}"


if __name__ == "__main__":
    mcp.run()
