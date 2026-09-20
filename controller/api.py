"""Small standard-library client for the current Agents API endpoints."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any, Callable

from .events import EventCapture, redact


class AgentApiError(RuntimeError):
    def __init__(self, operation: str, status: int | None, detail: str) -> None:
        self.operation = operation
        self.status = status
        self.detail = detail
        super().__init__(f"{operation} failed ({status or 'transport'}): {redact(detail)}")


class AgentApiClient:
    def __init__(
        self,
        api_key: str,
        capture: EventCapture,
        project_id: str,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self._api_key = api_key
        self._capture = capture
        self._project_id = project_id
        self._base_url = base_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        accept: str = "application/json",
    ) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "OpenAI-Beta": "agents=v1",
            "Accept": accept,
            "OpenAI-Project": self._project_id,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        self._capture.controller(
            "api_request",
            {"method": method, "path": path, "body": body, "accept": accept},
        )
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                content = response.read().decode("utf-8")
                parsed = json.loads(content) if content else {}
                self._capture.controller(
                    "api_response",
                    {"method": method, "path": path, "status": response.status},
                )
                return parsed
        except urllib.error.HTTPError as exc:
            detail = redact(exc.read().decode("utf-8", errors="replace"))
            self._capture.controller(
                "api_error",
                {"method": method, "path": path, "status": exc.code, "detail": detail},
            )
            raise AgentApiError(path, exc.code, str(detail)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            detail = redact(str(exc))
            self._capture.controller(
                "api_error",
                {"method": method, "path": path, "status": None, "detail": detail},
            )
            raise AgentApiError(path, None, str(detail)) from exc

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/agents/sessions", payload)

    def send_message(self, session_id: str, message: str) -> dict[str, Any]:
        body = {
            "events": [
                {
                    "type": "agent.session.input.message",
                    "input": [
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": message}],
                        }
                    ],
                }
            ]
        }
        return self._request("POST", f"/agents/sessions/{session_id}/events", body)

    def retrieve_session(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/agents/sessions/{session_id}")

    def list_items(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/agents/sessions/{session_id}/items?order=asc&limit=100",
        )

    def stream_events(
        self,
        session_id: str,
        on_open: Callable[[], None] | None = None,
    ) -> Iterator[tuple[str | None, Any]]:
        """Yield parsed SSE payloads while preserving the raw event name."""

        url = f"{self._base_url}/agents/sessions/{session_id}/events"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "OpenAI-Beta": "agents=v1",
                "OpenAI-Project": self._project_id,
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
            },
            method="GET",
        )
        self._capture.controller(
            "api_stream_open",
            {"method": "GET", "path": f"/agents/sessions/{session_id}/events"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if on_open is not None:
                    on_open()
                event_name: str | None = None
                data_lines: list[str] = []
                while True:
                    try:
                        line = response.readline()
                    except socket.timeout:
                        continue
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
                    if decoded.startswith("event:"):
                        event_name = decoded[6:].strip() or None
                    elif decoded.startswith("data:"):
                        data_lines.append(decoded[5:].lstrip())
                    elif decoded == "" and data_lines:
                        raw = "\n".join(data_lines)
                        data_lines = []
                        if raw == "[DONE]":
                            yield event_name, raw
                        else:
                            try:
                                parsed: Any = json.loads(raw)
                            except json.JSONDecodeError:
                                parsed = raw
                            yield event_name, parsed
                        event_name = None
                if data_lines:
                    raw = "\n".join(data_lines)
                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError:
                        parsed = raw
                    yield event_name, parsed
        except urllib.error.HTTPError as exc:
            detail = redact(exc.read().decode("utf-8", errors="replace"))
            raise AgentApiError("event stream", exc.code, str(detail)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AgentApiError("event stream", None, str(redact(str(exc)))) from exc
