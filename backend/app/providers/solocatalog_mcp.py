"""SoloCatalog Streamable HTTP MCP adapter. Uses only the provider's documented tools."""
from __future__ import annotations

import json
from typing import Any

import httpx


class SoloCatalogError(Exception):
    def __init__(self, code: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class SoloCatalogMCPAdapter:
    def __init__(self, url: str, api_key: str = "", timeout_seconds: float = 25.0):
        if not url.startswith("https://"):
            raise ValueError("SoloCatalog MCP URL must use HTTPS")
        self.url = url
        self.api_key = api_key.strip()
        self.timeout = timeout_seconds

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            raise SoloCatalogError(
                f"http_{response.status_code}",
                f"SoloCatalog MCP returned HTTP {response.status_code}.",
                response.status_code,
            )
        body = response.text.strip()
        if not body:
            return {}
        if "text/event-stream" in response.headers.get("content-type", ""):
            data = [line[5:].strip() for line in body.splitlines() if line.startswith("data:")]
            if not data:
                raise SoloCatalogError("invalid_response", "SoloCatalog MCP returned an empty event stream.")
            body = data[-1]
        try:
            value = json.loads(body)
        except ValueError:
            raise SoloCatalogError("invalid_response", "SoloCatalog MCP returned invalid JSON.") from None
        if not isinstance(value, dict):
            raise SoloCatalogError("invalid_response", "SoloCatalog MCP returned an unexpected response.")
        return value

    async def _post(self, client: httpx.AsyncClient, payload: dict, session_id: str | None = None):
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if session_id:
            headers["Mcp-Session-Id"] = session_id
            headers["MCP-Protocol-Version"] = "2025-03-26"
        try:
            response = await client.post(self.url, headers=headers, json=payload)
        except httpx.TimeoutException:
            raise SoloCatalogError("timeout", "SoloCatalog MCP request timed out.") from None
        except httpx.RequestError:
            raise SoloCatalogError("unavailable", "SoloCatalog MCP is unreachable.") from None
        return self._parse_response(response), response.headers.get("Mcp-Session-Id", session_id)

    @staticmethod
    def _extract_data(result: dict[str, Any]) -> Any:
        if isinstance(result.get("structuredContent"), (dict, list)):
            return result["structuredContent"]
        blocks = result.get("content")
        if isinstance(blocks, list):
            texts = [item.get("text", "") for item in blocks if isinstance(item, dict) and item.get("type") == "text"]
            if len(texts) == 1:
                try:
                    return json.loads(texts[0])
                except ValueError:
                    return texts[0]
            if texts:
                parsed = []
                for value in texts:
                    try:
                        parsed.append(json.loads(value))
                    except ValueError:
                        parsed.append(value)
                return parsed
        return result

    async def _call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            init, session_id = await self._post(client, {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "ai-manager", "version": "2.4.11"},
                },
            })
            if init.get("error"):
                raise SoloCatalogError("initialize_failed", "SoloCatalog MCP initialization failed.")
            await self._post(client, {
                "jsonrpc": "2.0", "method": "notifications/initialized", "params": {},
            }, session_id)
            listed, session_id = await self._post(client, {
                "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
            }, session_id)
            tools = listed.get("result", {}).get("tools", [])
            tool = next((item for item in tools if item.get("name") == tool_name), None)
            if not tool:
                raise SoloCatalogError("unsupported_operation", f"SoloCatalog does not expose {tool_name}.")
            schema = tool.get("inputSchema", {}) or {}
            properties = schema.get("properties", {})
            safe_args = {key: value for key, value in arguments.items() if value is not None and key in properties}
            missing = [key for key in schema.get("required", []) if key not in safe_args]
            if missing:
                raise SoloCatalogError("missing_arguments", f"SoloCatalog {tool_name} requires additional parameters.")
            called, _ = await self._post(client, {
                "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": tool_name, "arguments": safe_args},
            }, session_id)
            if called.get("error"):
                raise SoloCatalogError("tool_error", f"SoloCatalog {tool_name} failed.")
            result = called.get("result", {})
            if result.get("isError"):
                raise SoloCatalogError("tool_error", f"SoloCatalog {tool_name} returned an error.")
            return {"tool": tool_name, "data": self._extract_data(result), "provider": "solocatalog_mcp"}

    async def decode(self, vin: str, lang: str = "en") -> Any:
        return await self._call("decode_vin", {"vin": vin, "lang": lang})

    async def lookup(
        self, *, vin: str, mode: str, query: str | None = None, lang: str = "en",
        brand: str | None = None, model: str | None = None, diagram: str | None = None,
    ) -> dict[str, Any]:
        if mode == "models":
            return await self._call("find_models", {"brand": brand, "q": query, "lang": lang})
        if mode == "diagrams":
            return await self._call("list_diagrams", {"vin": vin, "lang": lang})
        if mode == "diagram":
            return await self._call("get_diagram_parts", {"vin": vin, "model": model, "diagram": diagram, "lang": lang})
        if mode == "parts":
            return await self._call("search_parts", {"vin": vin, "q": query, "query": query, "part_name": query, "lang": lang})
        raise SoloCatalogError("unsupported_operation", f"SoloCatalog does not support {mode}.")
