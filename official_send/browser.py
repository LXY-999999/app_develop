from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

from playwright.async_api import Browser, BrowserContext, Locator, Page, Playwright, async_playwright

ActionKind = Literal["click", "fill", "press", "wait", "upload"]


@dataclass(slots=True)
class BrowserAction:
    kind: ActionKind
    selector: str | None = None
    text: str | None = None
    file_path: str | None = None
    key: str | None = None
    timeout_ms: int = 5_000


@dataclass(slots=True)
class BrowserElement:
    selector: str
    matched_selector: str
    index: int
    tag: str
    text: str
    role: str
    href: str
    placeholder: str
    aria_label: str
    visible: bool
    x: float
    y: float
    width: float
    height: float


@dataclass(slots=True)
class BrowserSnapshot:
    url: str
    title: str
    screenshot_path: str
    page_text: str
    elements: list[BrowserElement] = field(default_factory=list)


def resolve_chromium_executable() -> str | None:
    configured_path = os.getenv("OFFICIAL_SEND_BROWSER_EXECUTABLE")
    candidates = [
        configured_path,
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def chromium_launch_options(headless: bool) -> dict[str, Any]:
    options: dict[str, Any] = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-default-browser-check",
            "--disable-features=Translate",
        ],
        "ignore_default_args": ["--enable-automation"],
    }
    executable = resolve_chromium_executable()
    if executable:
        options["executable_path"] = executable
    return options


class BrowserComputerUse:
    def __init__(self, artifact_dir: Path, headless: bool = False) -> None:
        self._artifact_dir = artifact_dir
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self._step = 0
        self._response_cache: list[dict[str, Any]] = []

    async def __aenter__(self) -> "BrowserComputerUse":
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        launch_options = chromium_launch_options(headless=self._headless)
        executable = launch_options.get("executable_path", "(playwright bundled)")
        print(f"[official_send] launching browser: {executable} headless={self._headless}", flush=True)
        self._browser = await self._playwright.chromium.launch(**launch_options)
        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 1080},
        )
        self.page = await self._context.new_page()
        self.page.on("response", lambda response: asyncio.create_task(self._capture_response(response)))
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def navigate(self, url: str, timeout_ms: int = 30_000) -> str:
        assert self.page is not None
        await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        return self.page.url

    async def wait(self, seconds: float) -> None:
        assert self.page is not None
        await self.page.wait_for_timeout(int(seconds * 1000))

    async def act(self, action: BrowserAction) -> None:
        assert self.page is not None
        if action.kind == "wait":
            await self.page.wait_for_timeout(action.timeout_ms)
            return

        if action.kind == "press":
            if not action.key:
                raise ValueError("press action requires key")
            await self.page.keyboard.press(action.key)
            return

        if not action.selector:
            raise ValueError(f"{action.kind} action requires selector")
        locator = self.page.locator(action.selector).first
        await locator.wait_for(state="visible", timeout=action.timeout_ms)

        if action.kind == "click":
            await locator.click(timeout=action.timeout_ms)
            return
        if action.kind == "fill":
            await locator.fill(action.text or "", timeout=action.timeout_ms)
            return
        if action.kind == "upload":
            if not action.file_path:
                raise ValueError("upload action requires file_path")
            await locator.set_input_files(action.file_path, timeout=action.timeout_ms)
            return

        raise ValueError(f"Unsupported action kind: {action.kind}")

    async def snapshot(self, label: str) -> BrowserSnapshot:
        assert self.page is not None
        self._step += 1
        safe_label = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in label)
        screenshot_path = self._artifact_dir / f"{self._step:03d}_{safe_label}.png"
        last_error: Exception | None = None
        for _attempt in range(3):
            try:
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=3_000)
                except Exception:
                    pass
                await self.page.screenshot(path=str(screenshot_path), full_page=True)
                page_text = await self.page.locator("body").inner_text()
                elements = await self.page.evaluate(
                    """
                    () => {
                      const nodes = Array.from(
                        document.querySelectorAll(
                          "a,button,input,textarea,select,[role='button'],[tabindex]"
                        )
                      ).slice(0, 120);
                      const buildSelector = (node) => {
                        if (node.id) return `#${node.id}`;
                        const name = node.getAttribute("name");
                        if (name) return `${node.tagName.toLowerCase()}[name="${name}"]`;
                        const placeholder = node.getAttribute("placeholder");
                        if (placeholder) {
                          return `${node.tagName.toLowerCase()}[placeholder="${placeholder}"]`;
                        }
                        const text = (node.innerText || node.textContent || "").trim();
                        if (text) return `text=${text.slice(0, 40)}`;
                        return node.tagName.toLowerCase();
                      };

                      return nodes.map((node) => {
                        const rect = node.getBoundingClientRect();
                        return {
                          selector: buildSelector(node),
                          matched_selector: "",
                          index: 0,
                          tag: node.tagName.toLowerCase(),
                          text: (node.innerText || node.textContent || "").trim().slice(0, 80),
                          role: node.getAttribute("role") || "",
                          href: node.href || "",
                          placeholder: node.getAttribute("placeholder") || "",
                          aria_label: node.getAttribute("aria-label") || "",
                          visible: !!(rect.width > 0 && rect.height > 0),
                          x: rect.x,
                          y: rect.y,
                          width: rect.width,
                          height: rect.height
                        };
                      });
                    }
                    """,
                )
                return BrowserSnapshot(
                    url=self.page.url,
                    title=await self.page.title(),
                    screenshot_path=str(screenshot_path),
                    page_text=page_text[:20_000],
                    elements=[BrowserElement(**item) for item in elements],
                )
            except Exception as exc:
                last_error = exc
                await self.page.wait_for_timeout(400)
        assert last_error is not None
        raise last_error

    async def find_first_visible(
        self,
        selectors: list[str],
        timeout_ms: int = 1_500,
    ) -> Locator | None:
        assert self.page is not None
        if not selectors:
            return None

        # Treat timeout_ms as a total budget for the whole selector scan.
        # Large semantic selector dictionaries are expected in generic mode;
        # waiting the full timeout for every selector makes the agent look hung.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(timeout_ms, 0) / 1000

        for selector in selectors:
            locator = self.page.locator(selector).first
            try:
                if await locator.is_visible():
                    return locator
            except Exception:
                continue

        for selector in selectors:
            remaining_ms = int((deadline - loop.time()) * 1000)
            if remaining_ms <= 0:
                break
            locator = self.page.locator(selector).first
            try:
                await locator.wait_for(state="visible", timeout=min(remaining_ms, 120))
                return locator
            except Exception:
                continue
        return None

    async def current_url(self) -> str:
        assert self.page is not None
        return self.page.url

    async def page_signature(self) -> str:
        assert self.page is not None
        payload = await self.page.evaluate(
            """
            () => {
              const body = (document.body?.innerText || "").replace(/\\s+/g, " ").trim();
              const title = document.title || "";
              const start = body.slice(0, 600);
              const end = body.slice(-600);
              const nodeCount = document.querySelectorAll("body *").length;
              return `${location.href}||${title}||${nodeCount}||${start}||${end}`;
            }
            """,
        )
        return str(payload)

    async def _capture_response(self, response) -> None:
        try:
            request = response.request
            if request.resource_type not in {"xhr", "fetch"}:
                return
            content_type = response.headers.get("content-type", "")
            body_text = await response.text()
            if len(body_text) > 200_000:
                body_text = body_text[:200_000]
            parsed_body: Any = body_text
            if "json" in content_type.lower():
                try:
                    parsed_body = json.loads(body_text)
                except Exception:
                    parsed_body = body_text
            self._response_cache.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "content_type": content_type,
                    "body": parsed_body,
                }
            )
            if len(self._response_cache) > 25:
                self._response_cache = self._response_cache[-25:]
        except Exception:
            return

    async def scroll_by(self, dx: int = 0, dy: int = 0) -> dict[str, int]:
        assert self.page is not None
        payload = await self.page.evaluate(
            """
            ([deltaX, deltaY]) => {
              window.scrollBy(deltaX, deltaY);
              return {
                x: Math.round(window.scrollX || window.pageXOffset || 0),
                y: Math.round(window.scrollY || window.pageYOffset || 0)
              };
            }
            """,
            [dx, dy],
        )
        return {"x": int(payload["x"]), "y": int(payload["y"])}

    async def scroll_to(self, x: int = 0, y: int = 0) -> dict[str, int]:
        assert self.page is not None
        payload = await self.page.evaluate(
            """
            ([targetX, targetY]) => {
              window.scrollTo(targetX, targetY);
              return {
                x: Math.round(window.scrollX || window.pageXOffset || 0),
                y: Math.round(window.scrollY || window.pageYOffset || 0)
              };
            }
            """,
            [x, y],
        )
        return {"x": int(payload["x"]), "y": int(payload["y"])}

    async def page_contains_any_text(self, keywords: list[str]) -> bool:
        assert self.page is not None
        body = await self.page.locator("body").inner_text()
        return any(keyword in body for keyword in keywords)

    async def try_press_enter(self, locator: Locator) -> None:
        await locator.click()
        await asyncio.sleep(0.2)
        await locator.press("Enter")

    async def probe_selectors(
        self,
        selectors: list[str],
        max_per_selector: int = 5,
    ) -> list[BrowserElement]:
        assert self.page is not None
        results: list[BrowserElement] = []
        for selector in selectors:
            locator = self.page.locator(selector)
            try:
                count = await locator.count()
            except Exception:
                continue
            for index in range(min(count, max_per_selector)):
                node = locator.nth(index)
                try:
                    payload = await node.evaluate(
                        """
                        (element, meta) => {
                          const linked =
                            element.closest("a[href]") ||
                            element.querySelector?.("a[href]") ||
                            element.closest("[data-href],[data-url],[data-link],[router-link]") ||
                            element.querySelector?.("[data-href],[data-url],[data-link],[router-link]");
                          const linkedHref =
                            linked?.href ||
                            linked?.getAttribute?.("data-href") ||
                            linked?.getAttribute?.("data-url") ||
                            linked?.getAttribute?.("data-link") ||
                            linked?.getAttribute?.("router-link") ||
                            "";
                          const rect = element.getBoundingClientRect();
                          const text = (
                            element.innerText ||
                            element.textContent ||
                            element.value ||
                            ""
                          ).trim();
                          return {
                            selector: meta.selector,
                            matched_selector: meta.selector,
                            index: meta.index,
                            tag: element.tagName.toLowerCase(),
                            text: text.slice(0, 120),
                            role: element.getAttribute("role") || "",
                            href: element.href || linkedHref,
                            placeholder: element.getAttribute("placeholder") || "",
                            aria_label: element.getAttribute("aria-label") || "",
                            visible: !!(rect.width > 0 && rect.height > 0),
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                          };
                        }
                        """,
                        {"selector": selector, "index": index},
                    )
                except Exception:
                    continue
                if payload.get("visible"):
                    results.append(BrowserElement(**payload))
        return results

    async def probe_keywords(
        self,
        keywords: list[str],
        max_results: int = 20,
    ) -> list[BrowserElement]:
        assert self.page is not None
        if not keywords:
            return []
        payload = await self.page.evaluate(
            """
            ({ keywords, maxResults }) => {
              const lowered = keywords.map((item) => String(item || "").toLowerCase()).filter(Boolean);
              const isVisible = (node) => {
                const rect = node.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
              };
              const isClickable = (node) => {
                if (!node) return false;
                const tag = node.tagName.toLowerCase();
                if (["a", "button", "input", "select", "textarea", "summary"].includes(tag)) return true;
                if (node.getAttribute("role") === "button") return true;
                if (node.hasAttribute("onclick")) return true;
                if (node.hasAttribute("tabindex")) return true;
                return false;
              };
              const buildSelector = (node) => {
                if (node.id) return `#${CSS.escape(node.id)}`;
                const parts = [];
                let current = node;
                while (current && current.nodeType === Node.ELEMENT_NODE && current.tagName.toLowerCase() !== "html") {
                  let part = current.tagName.toLowerCase();
                  const parent = current.parentElement;
                  if (parent) {
                    const siblings = Array.from(parent.children).filter((sibling) => sibling.tagName === current.tagName);
                    if (siblings.length > 1) {
                      part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
                    }
                  }
                  parts.unshift(part);
                  current = current.parentElement;
                }
                return parts.join(" > ");
              };
              const linkedHref = (node) => {
                const linked =
                  node.closest("a[href]") ||
                  node.querySelector?.("a[href]") ||
                  node.closest("[data-href],[data-url],[data-link],[router-link]") ||
                  node.querySelector?.("[data-href],[data-url],[data-link],[router-link]");
                return (
                  linked?.href ||
                  linked?.getAttribute?.("data-href") ||
                  linked?.getAttribute?.("data-url") ||
                  linked?.getAttribute?.("data-link") ||
                  linked?.getAttribute?.("router-link") ||
                  ""
                );
              };
              const nodes = Array.from(document.querySelectorAll("body *"));
              const seen = new Set();
              const results = [];
              for (const node of nodes) {
                if (!isVisible(node)) continue;
                const blob = [
                  node.innerText || node.textContent || "",
                  node.getAttribute("aria-label") || "",
                  node.getAttribute("title") || "",
                  node.getAttribute("placeholder") || "",
                ].join(" ").trim();
                if (!blob) continue;
                const loweredBlob = blob.toLowerCase();
                if (!lowered.some((keyword) => loweredBlob.includes(keyword))) continue;
                let target = node;
                while (target && !isClickable(target) && target.parentElement) {
                  target = target.parentElement;
                }
                if (!target || !isVisible(target)) {
                  target = node;
                }
                const selector = buildSelector(target);
                if (!selector || seen.has(selector)) continue;
                seen.add(selector);
                const rect = target.getBoundingClientRect();
                results.push({
                  selector,
                  matched_selector: selector,
                  index: 0,
                  tag: target.tagName.toLowerCase(),
                  text: (target.innerText || target.textContent || "").trim().slice(0, 120),
                  role: target.getAttribute("role") || "",
                  href: target.href || linkedHref(target),
                  placeholder: target.getAttribute("placeholder") || "",
                  aria_label: target.getAttribute("aria-label") || "",
                  visible: true,
                  x: rect.x,
                  y: rect.y,
                  width: rect.width,
                  height: rect.height
                });
                if (results.length >= maxResults) break;
              }
              return results;
            }
            """,
            {"keywords": keywords, "maxResults": max_results},
        )
        return [BrowserElement(**item) for item in payload]

    async def probe_clickables(
        self,
        max_results: int = 80,
    ) -> list[BrowserElement]:
        assert self.page is not None
        payload = await self.page.evaluate(
            """
            ({ maxResults }) => {
              const isVisible = (node) => {
                const rect = node.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
              };
              const buildSelector = (node) => {
                if (node.id) return `#${CSS.escape(node.id)}`;
                const parts = [];
                let current = node;
                while (current && current.nodeType === Node.ELEMENT_NODE && current.tagName.toLowerCase() !== "html") {
                  let part = current.tagName.toLowerCase();
                  const parent = current.parentElement;
                  if (parent) {
                    const siblings = Array.from(parent.children).filter((sibling) => sibling.tagName === current.tagName);
                    if (siblings.length > 1) {
                      part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
                    }
                  }
                  parts.unshift(part);
                  current = current.parentElement;
                }
                return parts.join(" > ");
              };
              const selector = "a,button,input[type=button],input[type=submit],[role='button'],[onclick],[tabindex]";
              const nodes = Array.from(document.querySelectorAll(selector));
              const results = [];
              const seen = new Set();
              const linkedHref = (node) => {
                const linked =
                  node.closest("a[href]") ||
                  node.querySelector?.("a[href]") ||
                  node.closest("[data-href],[data-url],[data-link],[router-link]") ||
                  node.querySelector?.("[data-href],[data-url],[data-link],[router-link]");
                return (
                  linked?.href ||
                  linked?.getAttribute?.("data-href") ||
                  linked?.getAttribute?.("data-url") ||
                  linked?.getAttribute?.("data-link") ||
                  linked?.getAttribute?.("router-link") ||
                  ""
                );
              };
              for (const node of nodes) {
                if (!isVisible(node)) continue;
                const key = buildSelector(node);
                if (!key || seen.has(key)) continue;
                seen.add(key);
                const rect = node.getBoundingClientRect();
                results.push({
                  selector: key,
                  matched_selector: key,
                  index: 0,
                  tag: node.tagName.toLowerCase(),
                  text: (node.innerText || node.textContent || node.value || "").trim().slice(0, 120),
                  role: node.getAttribute("role") || "",
                  href: node.href || linkedHref(node),
                  placeholder: node.getAttribute("placeholder") || "",
                  aria_label: node.getAttribute("aria-label") || "",
                  visible: true,
                  x: rect.x,
                  y: rect.y,
                  width: rect.width,
                  height: rect.height
                });
                if (results.length >= maxResults) break;
              }
              return results;
            }
            """,
            {"maxResults": max_results},
        )
        return [BrowserElement(**item) for item in payload]

    async def probe_response_candidates(
        self,
        keywords: list[str],
        current_url: str,
        max_results: int = 20,
    ) -> list[dict[str, str]]:
        lowered_keywords = [item.lower() for item in keywords if item]
        if not lowered_keywords:
            return []

        def iter_objects(value: Any):
            if isinstance(value, dict):
                yield value
                for child in value.values():
                    yield from iter_objects(child)
            elif isinstance(value, list):
                for child in value:
                    yield from iter_objects(child)

        def stringify(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            if isinstance(value, (int, float, bool)):
                return str(value)
            if isinstance(value, dict):
                return " ".join(stringify(item) for item in value.values())
            if isinstance(value, list):
                return " ".join(stringify(item) for item in value)
            return ""

        def extract_urls(value: Any, base_url: str) -> list[str]:
            found: list[str] = []
            if isinstance(value, str):
                lowered = value.lower()
                if value.startswith("http://") or value.startswith("https://"):
                    found.append(value)
                elif any(token in lowered for token in ("detail", "position", "post", "job")) and (
                    value.startswith("/") or ".html" in lowered
                ):
                    found.append(urljoin(base_url, value))
            elif isinstance(value, dict):
                for child in value.values():
                    found.extend(extract_urls(child, base_url))
            elif isinstance(value, list):
                for child in value:
                    found.extend(extract_urls(child, base_url))
            return found

        candidates: list[dict[str, str]] = []
        seen: set[str] = set()
        for response in reversed(self._response_cache):
            body = response.get("body")
            base_url = str(response.get("url", current_url))
            for item in iter_objects(body):
                blob = stringify(item).lower()
                if not any(keyword in blob for keyword in lowered_keywords):
                    continue
                urls = extract_urls(item, base_url)
                scalar_text = " ".join(
                    value.strip()
                    for value in item.values()
                    if isinstance(value, str) and value.strip()
                )
                for href in urls:
                    if href in seen:
                        continue
                    seen.add(href)
                    candidates.append(
                        {
                            "href": href,
                            "text": scalar_text[:240],
                            "source_url": base_url,
                        }
                    )
                    if len(candidates) >= max_results:
                        return candidates
        return candidates
