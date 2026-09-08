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
    N8N_CHATBOT_VERIFY_TLS  (optional) "false" to skip TLS certificate verification
                            (default: verify). Only for an n8n behind a self-signed
                            certificate, and only on a network you trust.
"""

import json
import logging
import os
import re
import ssl
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated

import httpx2
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__

logger = logging.getLogger(__name__)

CHATBOT_URL = os.environ.get("N8N_CHATBOT_URL", "")
CHATBOT_TIMEOUT = int(os.environ.get("N8N_CHATBOT_TIMEOUT", "120"))

# TLS verification is on unless it is explicitly turned off. An n8n instance
# behind a self-signed certificate needs N8N_CHATBOT_VERIFY_TLS=false; nothing
# else should.
VERIFY_TLS = os.environ.get("N8N_CHATBOT_VERIFY_TLS", "true").strip().lower() not in (
    "false",
    "0",
    "no",
)
if not VERIFY_TLS:
    logger.warning(
        "N8N_CHATBOT_VERIFY_TLS=false: TLS sertifikası doğrulanmayacak (%s)", CHATBOT_URL
    )

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


@dataclass
class ChatConfig:
    """Everything discovered from the n8n Chat Trigger HTML page."""

    headers: dict[str, str] = field(default_factory=dict)
    name: str = ""
    description: str = ""
    initial_messages: list[str] = field(default_factory=list)


def _discover_chat_config() -> ChatConfig:
    """GET the chat UI HTML and extract instance headers, name, description."""
    config = ChatConfig()
    try:
        with httpx2.Client(timeout=15, verify=VERIFY_TLS) as client:
            resp = client.get(CHATBOT_URL)
            if resp.status_code != 200 or "text/html" not in resp.headers.get("content-type", ""):
                return config
            html = resp.text

            # X-Instance-Id
            m = re.search(r"['\"]X-Instance-Id['\"]\s*:\s*['\"]([^'\"]+)['\"]", html)
            if m:
                config.headers["X-Instance-Id"] = m.group(1)

            # i18n title & subtitle  (e.g. en: {"subtitle":"...","title":"..."})
            m = re.search(r"i18n:\s*\{[^}]*?(\{[^}]+\})", html)
            if m:
                try:
                    i18n = json.loads(m.group(1))
                    config.name = i18n.get("title", "").strip()
                    config.description = i18n.get("subtitle", "").strip()
                except json.JSONDecodeError:
                    pass

            # initialMessages
            m = re.search(r"initialMessages:\s*(\[[^\]]+\])", html)
            if m:
                try:
                    config.initial_messages = json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
    except Exception as exc:
        # Discovery is best-effort: the server still works with defaults.
        logger.warning("Chatbot yapılandırması keşfedilemedi (%s): %s", CHATBOT_URL, exc)
    return config


# Discovery runs once at import: the tool description is built from it, and
# descriptions are read when the tool is registered.
_chat_config = _discover_chat_config()

_CHATBOT_NAME = _chat_config.name or "n8n Chatbot"
_REQUEST_HEADERS = _chat_config.headers

# Description: auto-discovered + env var (additive)
_desc_parts: list[str] = []
if _chat_config.description:
    _desc_parts.append(_chat_config.description)
_extra_desc = os.environ.get("N8N_CHATBOT_DESCRIPTION", "")
if _extra_desc:
    _desc_parts.append(_extra_desc)
if _chat_config.initial_messages:
    _desc_parts.append(f"Karşılama: {_chat_config.initial_messages[0]}")

TOOL_DESCRIPTION = f"{_CHATBOT_NAME} chatbot'una soru sorar ve cevabını döner."
if _desc_parts:
    TOOL_DESCRIPTION += "\n" + "\n".join(_desc_parts)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    """Shared state for the lifetime of the server."""

    http: httpx2.AsyncClient
    config: ChatConfig


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    """Open one HTTP client for the whole server run."""
    async with httpx2.AsyncClient(timeout=CHATBOT_TIMEOUT, verify=VERIFY_TLS) as http:
        yield AppContext(http=http, config=_chat_config)


mcp = MCPServer("n8n-chatbot", version=__version__, lifespan=app_lifespan)


class ChatReply(BaseModel):
    """One answer from the chatbot."""

    answer: str = Field(description="Chatbot'un cevabı.")
    session_id: str = Field(
        description="Bu cevabın ait olduğu oturum. Aynı konuşmayı sürdürmek için "
        "sonraki çağrıda bu değeri geri gönder."
    )


@mcp.tool(
    description=TOOL_DESCRIPTION,
    title=f"{_CHATBOT_NAME}'a sor",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def ask_chatbot(
    question: Annotated[str, Field(description="Chatbot'a sorulacak soru.")],
    ctx: Context[AppContext],
    session_id: Annotated[
        str,
        Field(
            description="Opsiyonel oturum ID'si. Çoklu turlu konuşmalarda önceki cevabın "
            "session_id değerini geri gönder; boş bırakılırsa yeni bir oturum açılır."
        ),
    ] = "",
) -> ChatReply:
    app = ctx.request_context.lifespan_context
    resolved_session = session_id or str(uuid.uuid4())
    payload = {
        "action": "sendMessage",
        "chatInput": question,
        "sessionId": resolved_session,
    }

    logger.info("Chatbot çağrısı: session=%s", resolved_session)

    try:
        response = await app.http.post(CHATBOT_URL, json=payload, headers=app.config.headers)
        response.raise_for_status()
        data = response.json()
    except httpx2.TimeoutException as exc:
        raise ToolError(
            f"Chatbot {CHATBOT_TIMEOUT} saniye içinde yanıt vermedi."
        ) from exc
    except httpx2.HTTPStatusError as exc:
        raise ToolError(
            f"Chatbot HTTP {exc.response.status_code} hatası döndü."
        ) from exc
    except httpx2.ConnectError as exc:
        # httpx wraps a certificate failure in ConnectError, so the TLS case has
        # to be picked out of the cause chain to be named properly.
        if _is_tls_failure(exc):
            raise ToolError(
                f"Chatbot sunucusunun TLS sertifikası doğrulanamadı: {exc}. Sertifika kendinden "
                "imzalıysa ve ağa güveniyorsan N8N_CHATBOT_VERIFY_TLS=false ayarla."
            ) from exc
        raise ToolError(f"Chatbot sunucusuna bağlanılamadı: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ToolError("Chatbot geçerli JSON döndürmedi.") from exc

    return ChatReply(answer=_extract_answer(data), session_id=resolved_session)


def _is_tls_failure(exc: BaseException) -> bool:
    """Whether this connection error was really a certificate problem."""
    seen = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, ssl.SSLError):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def _extract_answer(data: object) -> str:
    """Pull the answer text out of whatever shape the n8n workflow returned."""
    if isinstance(data, dict):
        return str(data.get("output") or data.get("text") or data.get("response") or data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return str(first.get("output") or first.get("text") or first)
        return str(first)
    return str(data)


@mcp.resource(
    "n8n://config",
    name="Chatbot yapılandırması",
    description="n8n Chat Trigger sayfasından otomatik keşfedilen chatbot adı, "
    "açıklaması, karşılama mesajları ve istek başlıkları.",
    mime_type="application/json",
)
def chat_config_resource() -> str:
    """Expose what auto-discovery found, so a client can show or debug it."""
    return json.dumps(
        {
            "url": CHATBOT_URL,
            "name": _CHATBOT_NAME,
            "description": _chat_config.description,
            "initial_messages": _chat_config.initial_messages,
            "request_headers": sorted(_REQUEST_HEADERS),
            "timeout_seconds": CHATBOT_TIMEOUT,
            "verify_tls": VERIFY_TLS,
        },
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    mcp.run()
