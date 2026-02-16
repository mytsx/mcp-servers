#!/usr/bin/env python3
"""
n8n Chatbot MCP Server
Generic MCP server for any n8n Chat Trigger webhook.

Environment variables:
    N8N_CHATBOT_URL         (required) Full webhook URL, e.g. https://n8n.example.com/webhook/my-bot/chat
    N8N_CHATBOT_NAME        (optional) Display name, e.g. "HR Asistanı"
    N8N_CHATBOT_DESCRIPTION (optional) What the chatbot knows about, shown to the agent
    N8N_CHATBOT_TIMEOUT     (optional) Request timeout in seconds (default: 120)
"""

import os
import re
import sys
import uuid
import httpx
from mcp.server.fastmcp import FastMCP

CHATBOT_URL = os.environ.get("N8N_CHATBOT_URL", "")
CHATBOT_NAME = os.environ.get("N8N_CHATBOT_NAME", "n8n Chatbot")
CHATBOT_DESCRIPTION = os.environ.get("N8N_CHATBOT_DESCRIPTION", "")
CHATBOT_TIMEOUT = int(os.environ.get("N8N_CHATBOT_TIMEOUT", "120"))

if not CHATBOT_URL:
    print(
        "HATA: N8N_CHATBOT_URL environment variable zorunludur.\n"
        "Örnek: N8N_CHATBOT_URL=https://n8n.example.com/webhook/my-bot/chat",
        file=sys.stderr,
    )
    sys.exit(1)

mcp = FastMCP(CHATBOT_NAME)

# --- Auto-discover n8n instance config from chat UI HTML ---
_cached_headers: dict | None = None


def _discover_headers() -> dict:
    """GET the chat UI HTML and extract X-Instance-Id and any custom headers."""
    global _cached_headers
    if _cached_headers is not None:
        return _cached_headers

    headers = {}
    try:
        with httpx.Client(timeout=15, verify=False) as client:
            resp = client.get(CHATBOT_URL)
            if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                html = resp.text
                # Extract X-Instance-Id from webhookConfig headers in the JS
                match = re.search(r"['\"]X-Instance-Id['\"]\s*:\s*['\"]([^'\"]+)['\"]", html)
                if match:
                    headers["X-Instance-Id"] = match.group(1)
    except Exception:
        pass  # Not fatal - some n8n instances don't require it

    _cached_headers = headers
    return headers


# Build dynamic tool description
_desc_parts = [f"{CHATBOT_NAME} chatbot'una soru sorar ve cevabını döner."]
if CHATBOT_DESCRIPTION:
    _desc_parts.append(f"Bu chatbot şu konularda bilgi verebilir: {CHATBOT_DESCRIPTION}")
TOOL_DESCRIPTION = "\n".join(_desc_parts)


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

    headers = _discover_headers()

    try:
        with httpx.Client(timeout=CHATBOT_TIMEOUT, verify=False) as client:
            response = client.post(CHATBOT_URL, json=payload, headers=headers)
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
