from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.map_upload import (
    DeviceActiveMap,
    MapActivationRequest,
    MapArtifact,
    device_router,
    get_db,
)


CHECKSUM = "sha256:" + "a" * 64


class FakeResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class FakeSession:
    def __init__(self):
        self.known_device = True
        self.scalar_results = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, statement, params=None):
        return FakeResult((1,) if self.known_device else None)

    def scalar(self, statement):
        if not self.scalar_results:
            raise AssertionError("unexpected db.scalar() call")
        return self.scalar_results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def artifact(
    *,
    artifact_id=10,
    map_id=320,
    map_version=1,
    checksum=CHECKSUM,
    status="READY",
):
    return MapArtifact(
        id=artifact_id,
        product_type="crawler",
        device_id="crawler_00000001",
        map_id=map_id,
        map_version=map_version,
        map_name=str(map_id),
        checksum=checksum,
        file_size_bytes=100,
        storage_key=f"crawler/crawler_00000001/{map_id}/{map_version}/map.json",
        status=status,
    )


def make_app(db: FakeSession) -> FastAPI:
    app = FastAPI()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict) and "error" in exc.detail:
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

    app.include_router(device_router)
    return app


class MapActivationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {"MAP_UPLOAD_TOKEN": "test-token"},
        )
        self.env.start()

        self.db = FakeSession()
        self.client = TestClient(make_app(self.db))

    def tearDown(self):
        self.client.close()
        self.env.stop()

    def put(
        self,
        *,
        request_id="activate-1",
        map_id=320,
        map_version=1,
        checksum=CHECKSUM,
    ):
        return self.client.put(
            "/api/devices/crawler/crawler_00000001/active-map",
            headers={"Authorization": "Bearer test-token"},
            json={
                "requestId": request_id,
                "mapId": map_id,
                "mapVersion": map_version,
                "checksum": checksum,
            },
        )

    def test_first_activation_starts_revision_at_one(self):
        self.db.scalar_results = [
            None,
            artifact(),
            None,
        ]

        response = self.put()

        self.assertEqual(200, response.status_code)
        self.assertEqual("activated", response.json()["result"])
        self.assertEqual(1, response.json()["activeRevision"])
        self.assertEqual(320, response.json()["activeMap"]["mapId"])
        self.assertEqual(1, response.json()["activeMap"]["mapVersion"])

        active = next(
            item for item in self.db.added
            if isinstance(item, DeviceActiveMap)
        )
        request = next(
            item for item in self.db.added
            if isinstance(item, MapActivationRequest)
        )

        self.assertEqual(1, active.active_revision)
        self.assertEqual(10, active.artifact_id)
        self.assertEqual("activated", request.result)
        self.assertEqual(1, self.db.commits)

    def test_same_map_new_request_is_already_active_without_revision_increment(self):
        now = datetime.now(timezone.utc)
        active = DeviceActiveMap(
            product_type="crawler",
            device_id="crawler_00000001",
            artifact_id=10,
            active_revision=7,
            activation_request_id="old-request",
            activated_at=now,
            last_reported_at=now,
        )

        self.db.scalar_results = [
            None,
            artifact(),
            active,
        ]

        response = self.put(request_id="activate-2")

        self.assertEqual(200, response.status_code)
        self.assertEqual("already_active", response.json()["result"])
        self.assertEqual(7, response.json()["activeRevision"])
        self.assertEqual(7, active.active_revision)

    def test_new_map_increments_revision_once(self):
        now = datetime.now(timezone.utc)
        active = DeviceActiveMap(
            product_type="crawler",
            device_id="crawler_00000001",
            artifact_id=10,
            active_revision=7,
            activation_request_id="old-request",
            activated_at=now,
            last_reported_at=now,
        )

        self.db.scalar_results = [
            None,
            artifact(
                artifact_id=11,
                map_version=2,
            ),
            active,
        ]

        response = self.put(
            request_id="activate-v2",
            map_version=2,
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("activated", response.json()["result"])
        self.assertEqual(8, response.json()["activeRevision"])
        self.assertEqual(11, active.artifact_id)
        self.assertEqual(8, active.active_revision)

    def test_same_request_id_same_payload_replays_first_result(self):
        activated_at = datetime.now(timezone.utc)

        previous = MapActivationRequest(
            id=20,
            product_type="crawler",
            device_id="crawler_00000001",
            request_id="activate-1",
            map_id=320,
            map_version=1,
            checksum=CHECKSUM,
            result="activated",
            active_revision=5,
            activated_at=activated_at,
        )

        self.db.scalar_results = [previous]

        response = self.put()

        self.assertEqual(200, response.status_code)
        self.assertEqual("activated", response.json()["result"])
        self.assertEqual(5, response.json()["activeRevision"])
        self.assertEqual(0, self.db.commits)

    def test_same_request_id_different_payload_is_409(self):
        previous = MapActivationRequest(
            id=20,
            product_type="crawler",
            device_id="crawler_00000001",
            request_id="activate-1",
            map_id=320,
            map_version=1,
            checksum=CHECKSUM,
            result="activated",
            active_revision=5,
            activated_at=datetime.now(timezone.utc),
        )

        self.db.scalar_results = [previous]

        response = self.put(map_version=2)

        self.assertEqual(409, response.status_code)
        self.assertEqual(
            "IDEMPOTENCY_CONFLICT",
            response.json()["error"]["code"],
        )

    def test_missing_artifact_is_404(self):
        self.db.scalar_results = [
            None,
            None,
        ]

        response = self.put()

        self.assertEqual(404, response.status_code)
        self.assertEqual(
            "MAP_NOT_FOUND",
            response.json()["error"]["code"],
        )

    def test_not_ready_artifact_is_503(self):
        self.db.scalar_results = [
            None,
            artifact(status="UPLOADING"),
        ]

        response = self.put()

        self.assertEqual(503, response.status_code)
        self.assertEqual(
            "MAP_NOT_READY",
            response.json()["error"]["code"],
        )

    def test_checksum_mismatch_is_400(self):
        self.db.scalar_results = [
            None,
            artifact(),
        ]

        response = self.put(
            checksum="sha256:" + "b" * 64,
        )

        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "MAP_CHECKSUM_MISMATCH",
            response.json()["error"]["code"],
        )


if __name__ == "__main__":
    unittest.main()
