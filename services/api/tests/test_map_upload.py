from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.map_upload import MapArtifact, get_db, router


class FakeResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class FakeSession:
    def __init__(self):
        self.known_device = True
        self.existing: MapArtifact | None = None
        self.added: list[MapArtifact] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, statement, params=None):
        if self.known_device:
            return FakeResult((1,))
        return FakeResult(None)

    def scalar(self, statement):
        return self.existing

    def add(self, artifact):
        self.added.append(artifact)
        self.existing = artifact

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def make_app(db: FakeSession) -> FastAPI:
    app = FastAPI()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if (
            request.url.path.startswith("/api/maps/")
            and isinstance(exc.detail, dict)
            and "error" in exc.detail
        ):
            return JSONResponse(
                status_code=exc.status_code,
                content=jsonable_encoder(exc.detail),
                headers=exc.headers,
            )

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": jsonable_encoder(exc.detail)},
            headers=exc.headers,
        )

    app.include_router(router)
    return app


class MapUploadV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "MAP_UPLOAD_TOKEN": "test-token",
                "MAP_STATIC_ROOT": self.temp.name,
            },
        )
        self.env.start()

        self.db = FakeSession()
        self.client = TestClient(make_app(self.db))

        self.map_bytes = """{
  "map_id": 320,
  "version": 1,
  "frame": {},
  "cell_model": {},
  "blocks": [],
  "cells": [],
  "bridges": []
}""".encode("utf-8")

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.temp.cleanup()

    def request_bytes(self, map_bytes: bytes | None = None, **updates) -> bytes:
        original_map = self.map_bytes if map_bytes is None else map_bytes

        metadata = {
            "productType": "crawler",
            "deviceId": "crawler_00000001",
            "mapId": 320,
            "mapVersion": 1,
            "mapName": "320",
            "checksum": "sha256:" + hashlib.sha256(original_map).hexdigest(),
            "fileSizeBytes": len(original_map),
        }
        metadata.update(updates)

        prefix = json.dumps(
            metadata,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        return prefix[:-1] + b',"map":' + original_map + b"}"

    def post(self, body: bytes | None = None, token: str | None = "test-token"):
        headers = {"Content-Type": "application/json"}

        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        return self.client.post(
            "/api/maps/upload",
            content=self.request_bytes() if body is None else body,
            headers=headers,
        )

    def target(self) -> Path:
        return Path(
            self.temp.name,
            "crawler",
            "crawler_00000001",
            "320",
            "1",
            "map.json",
        )

    def test_first_upload_returns_201_created_and_preserves_bytes(self):
        response = self.post()

        self.assertEqual(201, response.status_code)

        checksum = "sha256:" + hashlib.sha256(self.map_bytes).hexdigest()

        self.assertEqual(
            {
                "result": "created",
                "artifact": {
                    "productType": "crawler",
                    "deviceId": "crawler_00000001",
                    "mapId": 320,
                    "mapVersion": 1,
                    "checksum": checksum,
                    "fileSizeBytes": len(self.map_bytes),
                    "status": "READY",
                },
            },
            response.json(),
        )

        self.assertEqual(self.map_bytes, self.target().read_bytes())
        self.assertEqual(1, len(self.db.added))
        self.assertEqual(1, self.db.commits)

        artifact = self.db.added[0]
        self.assertEqual(
            "crawler/crawler_00000001/320/1/map.json",
            artifact.storage_key,
        )
        self.assertEqual("READY", artifact.status)

    def test_same_version_same_checksum_returns_200_already_exists(self):
        first = self.post()
        second = self.post()

        self.assertEqual(201, first.status_code)
        self.assertEqual(200, second.status_code)
        self.assertEqual("already_exists", second.json()["result"])
        self.assertEqual(1, len(self.db.added))
        self.assertEqual(1, self.db.commits)

    def test_same_version_different_checksum_returns_409(self):
        self.assertEqual(201, self.post().status_code)

        changed = self.map_bytes.replace(
            b'"version": 1',
            b'"version": 1 ',
        )

        response = self.post(self.request_bytes(changed))

        self.assertEqual(409, response.status_code)
        self.assertEqual(
            "MAP_VERSION_CONFLICT",
            response.json()["error"]["code"],
        )
        self.assertEqual(self.map_bytes, self.target().read_bytes())

    def test_trailing_newline_is_preserved_and_hashed(self):
        source = self.map_bytes + b"\n"

        response = self.post(self.request_bytes(source))

        self.assertEqual(201, response.status_code)
        self.assertEqual(source, self.target().read_bytes())
        self.assertEqual(
            "sha256:" + hashlib.sha256(source).hexdigest(),
            response.json()["artifact"]["checksum"],
        )

    def test_missing_or_wrong_token_is_401(self):
        self.assertEqual(401, self.post(token=None).status_code)
        self.assertEqual(401, self.post(token="wrong").status_code)

    def test_unknown_product_or_device_is_403(self):
        self.db.known_device = False

        response = self.post()

        self.assertEqual(403, response.status_code)
        self.assertEqual("FORBIDDEN", response.json()["error"]["code"])

    def test_outer_and_inner_identity_mismatch_is_400(self):
        response = self.post(self.request_bytes(mapId=321))
        self.assertEqual(400, response.status_code)

        changed = self.map_bytes.replace(
            b'"version": 1',
            b'"version": 2',
        )
        response = self.post(self.request_bytes(changed))
        self.assertEqual(400, response.status_code)

    def test_uint32_limits_are_enforced(self):
        self.assertEqual(
            400,
            self.post(self.request_bytes(mapId=4294967296)).status_code,
        )
        self.assertEqual(
            400,
            self.post(self.request_bytes(mapVersion=4294967296)).status_code,
        )

    def test_size_and_checksum_use_original_map_bytes(self):
        response = self.post(
            self.request_bytes(fileSizeBytes=999)
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "MAP_CHECKSUM_MISMATCH",
            response.json()["error"]["code"],
        )

        wrong = "sha256:" + "0" * 64
        response = self.post(
            self.request_bytes(checksum=wrong)
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "MAP_CHECKSUM_MISMATCH",
            response.json()["error"]["code"],
        )

    def test_map_must_be_final_and_unique(self):
        valid = self.request_bytes()

        not_final = valid[:-1] + b',"after":true}'
        self.assertEqual(400, self.post(not_final).status_code)

        duplicate = valid[:-1] + b',"map":{}}'
        self.assertEqual(400, self.post(duplicate).status_code)

    def test_formatting_difference_is_content_conflict(self):
        self.assertEqual(201, self.post().status_code)

        compact = json.dumps(
            json.loads(self.map_bytes),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        self.assertNotEqual(self.map_bytes, compact)

        response = self.post(self.request_bytes(compact))

        self.assertEqual(409, response.status_code)
        self.assertEqual(
            "MAP_VERSION_CONFLICT",
            response.json()["error"]["code"],
        )

    def test_atomic_replace_failure_leaves_no_target_or_temp_file(self):
        with patch(
            "app.map_upload.os.replace",
            side_effect=OSError("disk failure"),
        ):
            response = self.post()

        self.assertEqual(500, response.status_code)
        self.assertEqual(
            "MAP_STORAGE_ERROR",
            response.json()["error"]["code"],
        )

        directory = self.target().parent
        self.assertFalse(self.target().exists())

        if directory.exists():
            self.assertEqual([], list(directory.glob("*.tmp")))

        self.assertEqual([], self.db.added)


if __name__ == "__main__":
    unittest.main()
