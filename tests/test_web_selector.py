import logging
from html import escape
import re
import unittest
from time import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from tests.migration_support import ROOT, source_functions


class WebSelectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.aria2 = SimpleNamespace(
            getFiles=AsyncMock(return_value=[]),
            getOption=AsyncMock(return_value={"dir": "/downloads"}),
        )
        self.set_aria2 = AsyncMock()
        self.namespace = source_functions(
            "web/wserver.py",
            {
                "_derive_pin",
                "_verify_pin",
                "_pin_rate_limited",
                "_record_pin_attempt",
                "handle_torrent",
                "handle_legacy_torrent",
                "legacy_files",
                "http_error",
                "server_error",
            },
            {
                "Request": Request,
                "JSONResponse": JSONResponse,
                "HTMLResponse": HTMLResponse,
                "HTTPException": HTTPException,
                "escape": escape,
                "LOGGER": logging.getLogger("selector-tests"),
                "_SAFE_GID": re.compile(r"^[A-Za-z0-9_-]{1,64}$"),
                "_SAFE_PIN": re.compile(r"^\d{4}$"),
                "_BOT_ID": "123456",
                "_PIN_SALT": b"wzmlx_v3_pin_salt",
                "_PIN_LEN": 4,
                "_PIN_RATE_LIMIT": 5,
                "_PIN_RATE_WINDOW": 60,
                "_pin_attempts": {},
                "time": time,
                "aria2": self.aria2,
                "make_tree": Mock(
                    return_value={
                        "files": [],
                        "engine": "aria2",
                        "error": "",
                        "message": "",
                    }
                ),
                "extract_file_ids": Mock(return_value=(["1", "3"], ["2"])),
                "set_aria2": self.set_aria2,
                "ClientError": RuntimeError,
                "TimeoutError": TimeoutError,
                "AQError": RuntimeError,
                "templates": Jinja2Templates(directory=str(ROOT / "web/templates")),
            },
        )
        self.app = FastAPI()
        self.app.add_exception_handler(HTTPException, self.namespace["http_error"])
        self.app.add_exception_handler(Exception, self.namespace["server_error"])
        self.app.add_api_route(
            "/app/files/torrent",
            self.namespace["handle_torrent"],
            methods=["GET", "POST"],
        )
        self.app.add_api_route(
            "/legacy/files/torrent",
            self.namespace["handle_legacy_torrent"],
            methods=["GET", "POST"],
        )
        self.app.add_api_route(
            "/legacy/files", self.namespace["legacy_files"], methods=["GET"]
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://test",
        )
        self.addAsyncCleanup(self.client.aclose)
        self.gid = "a1b2c3d4e5f6abcd"
        self.pin = self.namespace["_derive_pin"](self.gid)

    async def test_both_interfaces_read_files_with_same_pin(self):
        for base in ("/app/files", "/legacy/files"):
            response = await self.client.get(
                f"{base}/torrent", params={"gid": self.gid, "pin": self.pin}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["engine"], "aria2")
        self.assertEqual(self.aria2.getFiles.await_count, 2)

    async def test_legacy_selection_uses_upstream_submission(self):
        response = await self.client.post(
            "/legacy/files/torrent",
            params={"gid": self.gid, "pin": self.pin, "mode": "selection"},
            json=[],
        )
        self.assertEqual(response.json()["error"], "")
        self.set_aria2.assert_awaited_once_with(self.gid, "1,3")

    async def test_legacy_rejects_predictable_old_pin(self):
        old_pin = "".join(c for c in self.gid if c.isdigit())[:4]
        self.assertNotEqual(old_pin, self.pin)
        response = await self.client.get(
            "/legacy/files/torrent", params={"gid": self.gid, "pin": old_pin}
        )
        self.assertEqual(response.json()["error"], "Invalid pin")
        self.aria2.getFiles.assert_not_awaited()

    async def test_invalid_gid_cannot_reach_download_engine(self):
        response = await self.client.get(
            "/legacy/files/torrent", params={"gid": "../../etc/passwd", "pin": self.pin}
        )
        self.assertEqual(response.json()["error"], "Invalid GID")
        self.aria2.getFiles.assert_not_awaited()

    async def test_rate_limit_is_shared_between_interfaces(self):
        wrong_pin = "0000" if self.pin != "0000" else "9999"
        for _ in range(5):
            await self.client.get(
                "/legacy/files/torrent", params={"gid": self.gid, "pin": wrong_pin}
            )
        response = await self.client.get(
            "/app/files/torrent", params={"gid": self.gid, "pin": self.pin}
        )
        self.assertEqual(response.status_code, 429)
        self.aria2.getFiles.assert_not_awaited()

    async def test_missing_pin_is_rejected(self):
        response = await self.client.get(
            "/legacy/files/torrent", params={"gid": self.gid}
        )
        self.assertEqual(response.json()["error"], "Pin is missing")

    async def test_legacy_html_renders(self):
        response = await self.client.get("/legacy/files")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/legacy/files/torrent", response.text)

    async def test_legacy_backend_failure_returns_json_to_the_ui(self):
        self.set_aria2.side_effect = RuntimeError("test engine failure")
        response = await self.client.post(
            "/legacy/files/torrent",
            params={"gid": self.gid, "pin": self.pin, "mode": "selection"},
            json=[],
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"], "Internal server error")


if __name__ == "__main__":
    unittest.main()
