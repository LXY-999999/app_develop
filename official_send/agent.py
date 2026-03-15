from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .browser import BrowserAction, BrowserComputerUse
from .imessage import IMessageCodeWatcher
from .mcp_client import StdioMcpClient
from .tool_runtime import ToolRegistry, ToolSpec


class OfficialSendAgentRuntime:
    def __init__(self, mcp_command: list[str] | None = None) -> None:
        self.registry = ToolRegistry()
        self._mcp_command = mcp_command or []
        self._mcp_client: StdioMcpClient | None = None

    async def __aenter__(self) -> "OfficialSendAgentRuntime":
        if self._mcp_command:
            self._mcp_client = StdioMcpClient(self._mcp_command)
            await self._mcp_client.__aenter__()
            for tool in await self._mcp_client.list_tools():
                self.registry.register(
                    ToolSpec(
                        name=f"mcp.{tool.name}",
                        description=tool.description or f"MCP tool {tool.name}",
                        source="mcp",
                        handler=self._build_mcp_handler(tool.name),
                    ),
                )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._mcp_client:
            await self._mcp_client.__aexit__(*args)

    def bind_local_tools(
        self,
        browser: BrowserComputerUse,
        watcher: IMessageCodeWatcher,
    ) -> None:
        self.registry.register(
            ToolSpec(
                name="browser.navigate",
                description="Navigate browser to a URL.",
                handler=lambda url, timeout_ms=30000: browser.navigate(url, timeout_ms=timeout_ms),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.wait",
                description="Wait for a number of seconds.",
                handler=lambda seconds: browser.wait(seconds),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.snapshot",
                description="Capture page screenshot and structured snapshot.",
                handler=lambda label: browser.snapshot(label),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.current_url",
                description="Return current browser URL.",
                handler=lambda: browser.current_url(),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.page_signature",
                description="Return a compact page state signature for change detection.",
                handler=lambda: browser.page_signature(),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.scroll_by",
                description="Scroll the current page by the provided delta.",
                handler=lambda dx=0, dy=0: browser.scroll_by(dx=dx, dy=dy),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.scroll_to",
                description="Scroll the current page to the provided absolute position.",
                handler=lambda x=0, y=0: browser.scroll_to(x=x, y=y),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.find_first_visible",
                description="Find the first visible element from a list of selectors.",
                handler=lambda selectors, timeout_ms=1500: browser.find_first_visible(
                    selectors,
                    timeout_ms=timeout_ms,
                ),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.click_selector",
                description="Click an element identified by selector.",
                handler=lambda selector, timeout_ms=5000: browser.act(
                    BrowserAction(kind="click", selector=selector, timeout_ms=timeout_ms),
                ),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.fill_selector",
                description="Fill text into an element identified by selector.",
                handler=lambda selector, text, timeout_ms=5000: browser.act(
                    BrowserAction(
                        kind="fill",
                        selector=selector,
                        text=text,
                        timeout_ms=timeout_ms,
                    ),
                ),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.press_key",
                description="Press a keyboard key in the current page.",
                handler=lambda key: browser.act(BrowserAction(kind="press", key=key)),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.upload_file",
                description="Upload a file through an input[type=file] selector.",
                handler=lambda selector, file_path, timeout_ms=5000: browser.act(
                    BrowserAction(
                        kind="upload",
                        selector=selector,
                        file_path=file_path,
                        timeout_ms=timeout_ms,
                    ),
                ),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.page_contains_any_text",
                description="Return whether page body contains any of the given keywords.",
                handler=lambda keywords: browser.page_contains_any_text(keywords),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.probe_selectors",
                description="Return visible candidate elements for a list of selectors.",
                handler=lambda selectors, max_per_selector=5: browser.probe_selectors(
                    selectors,
                    max_per_selector=max_per_selector,
                ),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.probe_keywords",
                description="Return visible page-wide candidates matching semantic keywords.",
                handler=lambda keywords, max_results=20: browser.probe_keywords(
                    keywords,
                    max_results=max_results,
                ),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.probe_clickables",
                description="Return visible clickable elements across the page.",
                handler=lambda max_results=80: browser.probe_clickables(max_results=max_results),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="browser.probe_response_candidates",
                description="Return candidate URLs mined from recent XHR/fetch responses.",
                handler=lambda keywords, current_url, max_results=20: browser.probe_response_candidates(
                    keywords=keywords,
                    current_url=current_url,
                    max_results=max_results,
                ),
            ),
        )
        self.registry.register(
            ToolSpec(
                name="otp.wait_for_code",
                description="Poll iMessage for verification code.",
                handler=lambda **kwargs: self._wait_for_code_async(watcher, kwargs),
            ),
        )

    async def call(self, name: str, **kwargs: Any) -> Any:
        return await self.registry.call(name, **kwargs)

    def history(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.registry.history()]

    def _build_mcp_handler(self, tool_name: str):
        async def _handler(**kwargs: Any) -> Any:
            if not self._mcp_client:
                raise RuntimeError("MCP client not available")
            return await self._mcp_client.call_tool(tool_name, kwargs)

        return _handler

    async def _wait_for_code_async(
        self,
        watcher: IMessageCodeWatcher,
        kwargs: dict[str, Any],
    ) -> str:
        return watcher.wait_for_code(**kwargs)
