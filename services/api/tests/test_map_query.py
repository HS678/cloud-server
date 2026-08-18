from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import User, app, get_current_user
from app.database import get_db
from app.map_upload import DeviceActiveMap, MapArtifact


CHECKSUM = "sha256:" + "a" * 64


class FakeResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class FakeDevice:
    device_id = "crawler_00000001"
    product_type = "crawler"


class FakeBinding:
    role = "viewer"


class FakeSession:
    def __init__(self):
        self.active = None
        self.artifact = None
        self.access_allowed = True

    def execute(self, statement, params=None):
        if not self.access_allowed:
            return FakeResult(None)

        return FakeResult((FakeDevice(), FakeBinding()))

    def scalar(self, statement):
        text = str(statement)

        if "device_active_maps" in text:
            return self.active

        if "map_artifacts" in text:
            return self.artifact

        raise AssertionError(f"unexpected scalar query: {text}")

    def get(self, model, object_id):
        if model is MapArtifact:
            if self.artifact is not None and self.artifact.id == object_id:
                return self.artifact
            return None

        raise AssertionError(f"unexpected get: {model}")


def make_artifact(
    *,
    artifact_id=10,
    map_id=320,
    map_version=1,
    status="READY",
    storage_key="crawler/crawler_00000001/320/1/map.json",
):
    return MapArtifact(
        id=artifact_id,
        product_type="crawler",
        device_id="crawler_00000001",
        map_id=map_id,
        map_version=map_version,
        map_name="320",
        checksum=CHECKSUM,
        file_size_bytes=100,
        storage_key=storage_key,
        status=status,
    )


def make_active():
    now = datetime.now(timezone.utc)

    return DeviceActiveMap(
        product_type="crawler",
        device_id="crawler_00000001",
        artifact_id=10,
        active_revision=3,
        activation_request_id="activate-3",
        activated_at=now,
        last_reported_at=now,
    )


class MapQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

        self.env = patch.dict(
            os.environ,
            {"MAP_STATIC_ROOT": self.temp.name},
        )
        self.env.start()

        self.db = FakeSession()

        self.user = User(
            id=1,
            email="test@vgsolar.com",
            password_hash="unused",
            created_at=datetime.now(timezone.utc),
            display_name="tester",
            status="active",
        )

        def override_get_db():
            yield self.db

        def override_get_current_user():
            return self.user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user

        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.env.stop()
        self.temp.cleanup()

    def test_current_returns_active_map_and_no_store(self):
        self.db.active = make_active()
        self.db.artifact = make_artifact()

        response = self.client.get(
            "/api/devices/crawler/crawler_00000001/maps/current"
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("no-store", response.headers["cache-control"])

        body = response.json()

        self.assertEqual("crawler", body["productType"])
        self.assertEqual("crawler_00000001", body["deviceId"])
        self.assertEqual(3, body["activeRevision"])
        self.assertEqual(320, body["activeMap"]["mapId"])
        self.assertEqual(1, body["activeMap"]["mapVersion"])
        self.assertEqual(CHECKSUM, body["activeMap"]["checksum"])
        self.assertEqual(
            "/api/devices/crawler/crawler_00000001/maps/320/versions/1/content",
            body["activeMap"]["contentUrl"],
        )

    def test_current_without_activation_returns_404(self):
        self.db.active = None

        response = self.client.get(
            "/api/devices/crawler/crawler_00000001/maps/current"
        )

        self.assertEqual(404, response.status_code)
        self.assertEqual(
            "ACTIVE_MAP_NOT_SET",
            response.json()["error"]["code"],
        )

    def test_exact_metadata_returns_ready_artifact(self):
        self.db.artifact = make_artifact()

        response = self.client.get(
            "/api/devices/crawler/crawler_00000001/maps/320/versions/1"
        )

        self.assertEqual(200, response.status_code)

        body = response.json()

        self.assertEqual(320, body["mapId"])
        self.assertEqual(1, body["mapVersion"])
        self.assertEqual("READY", body["status"])
        self.assertEqual(CHECKSUM, body["checksum"])

    def test_exact_metadata_missing_returns_404(self):
        self.db.artifact = None

        response = self.client.get(
            "/api/devices/crawler/crawler_00000001/maps/320/versions/1"
        )

        self.assertEqual(404, response.status_code)
        self.assertEqual(
            "MAP_NOT_FOUND",
            response.json()["error"]["code"],
        )

    def test_content_returns_exact_original_bytes_and_cache_headers(self):
        content = b'{\n  "map_id": 320,\n  "version": 1\n}\n'

        target = Path(
            self.temp.name,
            "crawler",
            "crawler_00000001",
            "320",
            "1",
            "map.json",
        )
        target.parent.mkdir(parents=True)
        target.write_bytes(content)

        self.db.artifact = make_artifact()

        response = self.client.get(
            "/api/devices/crawler/crawler_00000001/maps/320/versions/1/content"
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(content, response.content)
        self.assertEqual(f'"{CHECKSUM}"', response.headers["etag"])
        self.assertEqual(
            "private, max-age=31536000, immutable",
            response.headers["cache-control"],
        )

    def test_content_etag_returns_304_after_auth(self):
        self.db.artifact = make_artifact()

        response = self.client.get(
            "/api/devices/crawler/crawler_00000001/maps/320/versions/1/content",
            headers={"If-None-Match": f'"{CHECKSUM}"'},
        )

        self.assertEqual(304, response.status_code)
        self.assertEqual(b"", response.content)
        self.assertEqual(f'"{CHECKSUM}"', response.headers["etag"])

    def test_product_type_mismatch_is_404(self):
        response = self.client.get(
            "/api/devices/other/crawler_00000001/maps/current"
        )

        self.assertEqual(404, response.status_code)
        self.assertEqual(
            "MAP_NOT_FOUND",
            response.json()["error"]["code"],
        )

    def test_device_without_user_access_is_not_readable(self):
        self.db.access_allowed = False

        response = self.client.get(
            "/api/devices/crawler/crawler_00000001/maps/current"
        )

        self.assertEqual(404, response.status_code)


if __name__ == "__main__":
    unittest.main()
