from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class McpTool:
    name: str
    description: str
    input_schema: dict[str, Any]


class StdioMcpClient:
    def __init__(self, command: list[str]) -> None:
        self._command = command
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0

    async def __aenter__(self) -> "StdioMcpClient":
        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "official_send", "version": "0.1.0"},
            },
        )
        await self._notify(
            "notifications/initialized",
            {},
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._process and self._process.stdin:
            self._process.stdin.close()
        if self._process:
            await self._process.wait()

    async def list_tools(self) -> list[McpTool]:
        payload = await self._request("tools/list", {})
        tools = payload.get("tools", [])
        return [
            McpTool(
                name=item.get("name", ""),
                description=item.get("description", ""),
                input_schema=item.get("inputSchema", {}),
            )
            for item in tools
            if item.get("name")
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        payload = await self._request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )
        return payload

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            },
        )
        while True:
            message = await self._read_message()
            if "id" not in message:
                continue
            if message["id"] != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"MCP error: {message['error']}")
            return message.get("result", {})

    async def _send(self, payload: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise RuntimeError("MCP process not started")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        self._process.stdin.write(header + body)
        await self._process.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        if not self._process or not self._process.stdout:
            raise RuntimeError("MCP process not started")

        headers: dict[str, str] = {}
        while True:
            line = await self._process.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed stdout")
            decoded = line.decode("utf-8").strip()
            if not decoded:
                break
            key, _, value = decoded.partition(":")
            headers[key.lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            raise RuntimeError("Invalid MCP content-length")
        body = await self._process.stdout.readexactly(content_length)
        return json.loads(body.decode("utf-8"))

