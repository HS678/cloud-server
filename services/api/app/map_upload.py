"""Authenticated, byte-preserving storage for Robot map JSON uploads."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator
from sqlalchemy import BigInteger, DateTime, String, select, text as sql_text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base, get_db

SAFE_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
SHA256_CHECKSUM = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
DEFAULT_STATIC_ROOT = "/opt/cloud-server/storage/maps"
MAX_UPLOAD_BYTES = 32 * 1024 * 1024

router = APIRouter(prefix="/api/maps", tags=["maps"])
upload_bearer = HTTPBearer(auto_error=False)
_write_lock = threading.Lock()


class MapUploadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    product_type: str = Field(alias="productType", min_length=1)
    device_id: str = Field(alias="deviceId", min_length=1)
    map_id: StrictInt = Field(alias="mapId", ge=0, le=4294967295)
    map_version: StrictInt = Field(alias="mapVersion", ge=0, le=4294967295)
    map_name: str | None = Field(default=None, alias="mapName")
    checksum: str
    file_size_bytes: StrictInt = Field(alias="fileSizeBytes", ge=0)
    map: dict[str, Any]

    @field_validator("product_type", "device_id")
    @classmethod
    def validate_path_component(cls, value: str) -> str:
        if not SAFE_PATH_COMPONENT.fullmatch(value) or value in {".", ".."}:
            raise ValueError("must contain only letters, digits, '.', '_' or '-'")
        return value

    @field_validator("checksum")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        if not SHA256_CHECKSUM.fullmatch(value):
            raise ValueError("must use sha256:<64 hexadecimal characters>")
        return value.lower()


class MapArtifact(Base):
    __tablename__ = "map_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_type: Mapped[str] = mapped_column(String(64))
    device_id: Mapped[str] = mapped_column(String(64))
    map_id: Mapped[int] = mapped_column(BigInteger)
    map_version: Mapped[int] = mapped_column(BigInteger)
    map_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    checksum: Mapped[str] = mapped_column(String(71))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True))


class DeviceActiveMap(Base):
    __tablename__ = "device_active_maps"

    product_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[int] = mapped_column(BigInteger)
    active_revision: Mapped[int] = mapped_column(BigInteger)
    activation_request_id: Mapped[str] = mapped_column(String(255))
    activated_at: Mapped[Any] = mapped_column(DateTime(timezone=True))
    last_reported_at: Mapped[Any] = mapped_column(DateTime(timezone=True))


class MapActivationRequest(Base):
    __tablename__ = "map_activation_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_type: Mapped[str] = mapped_column(String(64))
    device_id: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(255))
    map_id: Mapped[int] = mapped_column(BigInteger)
    map_version: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(71))
    result: Mapped[str] = mapped_column(String(32))
    active_revision: Mapped[int] = mapped_column(BigInteger)
    activated_at: Mapped[Any] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True))


class MapActivationBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    request_id: str = Field(alias="requestId", min_length=1, max_length=255)
    map_id: StrictInt = Field(alias="mapId", ge=0, le=4294967295)
    map_version: StrictInt = Field(alias="mapVersion", ge=0, le=4294967295)
    checksum: str

    @field_validator("checksum")
    @classmethod
    def validate_activation_checksum(cls, value: str) -> str:
        if not SHA256_CHECKSUM.fullmatch(value):
            raise ValueError("must use sha256:<64 hexadecimal characters>")
        return value.lower()


class ActiveMapResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    map_id: int = Field(alias="mapId")
    map_version: int = Field(alias="mapVersion")
    checksum: str


class MapActivationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    result: str
    device_id: str = Field(alias="deviceId")
    active_revision: int = Field(alias="activeRevision")
    active_map: ActiveMapResponse = Field(alias="activeMap")
    activated_at: datetime = Field(alias="activatedAt")


class MapArtifactResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_type: str = Field(alias="productType")
    device_id: str = Field(alias="deviceId")
    map_id: int = Field(alias="mapId")
    map_version: int = Field(alias="mapVersion")
    checksum: str
    file_size_bytes: int = Field(alias="fileSizeBytes")
    status: str


class MapUploadResponse(BaseModel):
    result: str
    artifact: MapArtifactResponse


def _skip_whitespace(raw: bytes, index: int) -> int:
    while index < len(raw) and raw[index] in b" \t\r\n":
        index += 1
    return index


def _skip_json_string(raw: bytes, index: int) -> int:
    if index >= len(raw) or raw[index] != ord('"'):
        raise ValueError("expected JSON string")
    index += 1
    escaped = False
    while index < len(raw):
        byte = raw[index]
        if escaped:
            escaped = False
        elif byte == ord("\\"):
            escaped = True
        elif byte == ord('"'):
            return index + 1
        index += 1
    raise ValueError("unterminated JSON string")


def _skip_json_value(raw: bytes, index: int) -> int:
    index = _skip_whitespace(raw, index)
    if index >= len(raw):
        raise ValueError("missing JSON value")
    if raw[index] == ord('"'):
        return _skip_json_string(raw, index)
    if raw[index] not in (ord("{"), ord("[")):
        while index < len(raw) and raw[index] not in b",}":
            index += 1
        return index

    stack = [raw[index]]
    index += 1
    while index < len(raw) and stack:
        byte = raw[index]
        if byte == ord('"'):
            index = _skip_json_string(raw, index)
            continue
        if byte in (ord("{"), ord("[")):
            stack.append(byte)
        elif byte == ord("}"):
            if stack[-1] != ord("{"):
                raise ValueError("mismatched JSON brackets")
            stack.pop()
        elif byte == ord("]"):
            if stack[-1] != ord("["):
                raise ValueError("mismatched JSON brackets")
            stack.pop()
        index += 1
    if stack:
        raise ValueError("unterminated JSON value")
    return index


def extract_map_content(raw_body: bytes) -> tuple[dict[str, Any], bytes]:
    if not raw_body or len(raw_body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="invalid upload body size")
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid JSON upload envelope") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="upload envelope must be an object")

    try:
        index = _skip_whitespace(raw_body, 0)
        if index >= len(raw_body) or raw_body[index] != ord("{"):
            raise ValueError("expected object")
        index = _skip_whitespace(raw_body, index + 1)
        map_content: bytes | None = None
        while index < len(raw_body) and raw_body[index] != ord("}"):
            key_start = index
            key_end = _skip_json_string(raw_body, key_start)
            key = json.loads(raw_body[key_start:key_end])
            index = _skip_whitespace(raw_body, key_end)
            if index >= len(raw_body) or raw_body[index] != ord(":"):
                raise ValueError("expected colon")
            value_start = _skip_whitespace(raw_body, index + 1)
            value_end = _skip_json_value(raw_body, value_start)
            index = _skip_whitespace(raw_body, value_end)
            if key == "map":
                if map_content is not None or index >= len(raw_body) or raw_body[index] != ord("}"):
                    raise ValueError("map must be the final and unique field")
                # Robot embeds the source file bytes directly. Whitespace between the
                # parsed map value and the envelope's final brace therefore belongs
                # to the source file too (for example, its trailing newline).
                map_content = raw_body[value_start:index]
            if index < len(raw_body) and raw_body[index] == ord(","):
                index = _skip_whitespace(raw_body, index + 1)
            elif index < len(raw_body) and raw_body[index] == ord("}"):
                break
            else:
                raise ValueError("invalid object separator")
        if map_content is None:
            raise ValueError("missing map field")
        index = _skip_whitespace(raw_body, index + 1)
        if index != len(raw_body):
            raise ValueError("trailing data")
        map_object = json.loads(map_content)
        if not isinstance(map_object, dict) or map_object != payload.get("map"):
            raise ValueError("map payload mismatch")
        return payload, map_content
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid upload envelope") from exc


def require_upload_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(upload_bearer)],
) -> None:
    expected = os.getenv("MAP_UPLOAD_TOKEN", "")
    if (
        not expected
        or credentials is None
        or credentials.scheme.lower() != "bearer"
        or not hmac.compare_digest(credentials.credentials, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid map upload token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _validate_map_identity(body: MapUploadRequest) -> None:
    inner_id = body.map.get("map_id")
    inner_version = body.map.get("version")
    if type(inner_id) is not int or type(inner_version) is not int:
        raise HTTPException(status_code=400, detail="map.map_id and map.version must be integers")
    if inner_id < 0 or inner_version < 0:
        raise HTTPException(status_code=400, detail="map.map_id and map.version must be non-negative")
    if inner_id != body.map_id or inner_version != body.map_version:
        raise HTTPException(status_code=400, detail="outer and inner map ID/version do not match")


def _response(
    body: MapUploadRequest,
    size: int,
    checksum: str,
    result: str,
) -> MapUploadResponse:
    return MapUploadResponse(
        result=result,
        artifact=MapArtifactResponse(
            productType=body.product_type,
            deviceId=body.device_id,
            mapId=body.map_id,
            mapVersion=body.map_version,
            checksum=checksum,
            fileSizeBytes=size,
            status="READY",
        ),
    )


def _storage_key(body: MapUploadRequest) -> str:
    return (
        f"{body.product_type}/{body.device_id}/"
        f"{body.map_id}/{body.map_version}/map.json"
    )


def _require_known_device(
    db: Session,
    product_type: str,
    device_id: str,
) -> None:
    row = db.execute(
        sql_text(
            """
            SELECT 1
            FROM devices
            WHERE device_id = :device_id
              AND product_type = :product_type
            """
        ),
        {
            "device_id": device_id,
            "product_type": product_type,
        },
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "robot is not allowed to upload for this device",
                    "retryable": False,
                }
            },
        )


@router.post(
    "/upload",
    response_model=MapUploadResponse,
    response_model_by_alias=True,
)
async def upload_map(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_upload_token)],
) -> MapUploadResponse:
    raw_body = await request.body()

    if len(raw_body) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": "map upload exceeds maximum request size",
                    "retryable": False,
                }
            },
        )

    payload, content = extract_map_content(raw_body)

    try:
        body = MapUploadRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "invalid map upload request",
                    "retryable": False,
                    "details": exc.errors(include_context=False),
                }
            },
        ) from exc

    _require_known_device(
        db,
        body.product_type,
        body.device_id,
    )

    _validate_map_identity(body)

    actual_size = len(content)
    actual_checksum = f"sha256:{hashlib.sha256(content).hexdigest()}"

    if body.file_size_bytes != actual_size:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "MAP_CHECKSUM_MISMATCH",
                    "message": "fileSizeBytes does not match original map bytes",
                    "retryable": False,
                }
            },
        )

    if not hmac.compare_digest(body.checksum, actual_checksum):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "MAP_CHECKSUM_MISMATCH",
                    "message": "checksum does not match original map bytes",
                    "retryable": False,
                }
            },
        )

    existing = db.scalar(
        select(MapArtifact).where(
            MapArtifact.product_type == body.product_type,
            MapArtifact.device_id == body.device_id,
            MapArtifact.map_id == body.map_id,
            MapArtifact.map_version == body.map_version,
        )
    )

    if existing is not None:
        if not hmac.compare_digest(existing.checksum, actual_checksum):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "MAP_VERSION_CONFLICT",
                        "message": "mapId/mapVersion exists with a different checksum",
                        "retryable": False,
                    }
                },
            )

        response.status_code = status.HTTP_200_OK
        return _response(
            body,
            existing.file_size_bytes,
            existing.checksum,
            "already_exists",
        )

    root = Path(os.getenv("MAP_STATIC_ROOT", DEFAULT_STATIC_ROOT))
    storage_key = _storage_key(body)
    destination = root / storage_key
    temp_path: Path | None = None
    destination_created = False

    try:
        with _write_lock:
            if destination.exists():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": {
                            "code": "MAP_STORAGE_ERROR",
                            "message": "map storage contains an untracked version",
                            "retryable": False,
                        }
                    },
                )

            destination.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".map.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.replace(temp_path, destination)
            temp_path = None
            destination_created = True

            artifact = MapArtifact(
                product_type=body.product_type,
                device_id=body.device_id,
                map_id=body.map_id,
                map_version=body.map_version,
                map_name=body.map_name,
                checksum=actual_checksum,
                file_size_bytes=actual_size,
                storage_key=storage_key,
                status="READY",
            )

            db.add(artifact)

            try:
                db.commit()
            except Exception:
                db.rollback()
                if destination_created:
                    destination.unlink(missing_ok=True)
                    destination_created = False
                raise

    except HTTPException:
        raise
    except OSError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "MAP_STORAGE_ERROR",
                    "message": "failed to persist map",
                    "retryable": True,
                }
            },
        ) from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    response.status_code = status.HTTP_201_CREATED

    return _response(
        body,
        actual_size,
        actual_checksum,
        "created",
    )

device_router = APIRouter(prefix="/api/devices", tags=["maps"])


def _activation_response(
    *,
    result: str,
    device_id: str,
    active_revision: int,
    map_id: int,
    map_version: int,
    checksum: str,
    activated_at: datetime,
) -> MapActivationResponse:
    return MapActivationResponse(
        result=result,
        deviceId=device_id,
        activeRevision=active_revision,
        activeMap=ActiveMapResponse(
            mapId=map_id,
            mapVersion=map_version,
            checksum=checksum,
        ),
        activatedAt=activated_at,
    )


@device_router.put(
    "/{product_type}/{device_id}/active-map",
    response_model=MapActivationResponse,
    response_model_by_alias=True,
)
def activate_map(
    product_type: str,
    device_id: str,
    body: MapActivationBody,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_upload_token)],
) -> MapActivationResponse:
    _require_known_device(db, product_type, device_id)

    previous_request = db.scalar(
        select(MapActivationRequest).where(
            MapActivationRequest.product_type == product_type,
            MapActivationRequest.device_id == device_id,
            MapActivationRequest.request_id == body.request_id,
        )
    )

    if previous_request is not None:
        same_payload = (
            previous_request.map_id == body.map_id
            and previous_request.map_version == body.map_version
            and hmac.compare_digest(previous_request.checksum, body.checksum)
        )

        if not same_payload:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "IDEMPOTENCY_CONFLICT",
                        "message": "requestId was already used with different content",
                        "retryable": False,
                    }
                },
            )

        return _activation_response(
            result=previous_request.result,
            device_id=device_id,
            active_revision=previous_request.active_revision,
            map_id=previous_request.map_id,
            map_version=previous_request.map_version,
            checksum=previous_request.checksum,
            activated_at=previous_request.activated_at,
        )

    artifact = db.scalar(
        select(MapArtifact).where(
            MapArtifact.product_type == product_type,
            MapArtifact.device_id == device_id,
            MapArtifact.map_id == body.map_id,
            MapArtifact.map_version == body.map_version,
        )
    )

    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "MAP_NOT_FOUND",
                    "message": "map artifact does not exist",
                    "retryable": False,
                }
            },
        )

    if artifact.status != "READY":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "MAP_NOT_READY",
                    "message": "map artifact is not ready",
                    "retryable": True,
                }
            },
        )

    if not hmac.compare_digest(artifact.checksum, body.checksum):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MAP_CHECKSUM_MISMATCH",
                    "message": "activation checksum does not match stored artifact",
                    "retryable": False,
                }
            },
        )

    now = datetime.now(timezone.utc)

    active = db.scalar(
        select(DeviceActiveMap)
        .where(
            DeviceActiveMap.product_type == product_type,
            DeviceActiveMap.device_id == device_id,
        )
        .with_for_update()
    )

    if active is None:
        result = "activated"
        active_revision = 1
        activated_at = now

        active = DeviceActiveMap(
            product_type=product_type,
            device_id=device_id,
            artifact_id=artifact.id,
            active_revision=active_revision,
            activation_request_id=body.request_id,
            activated_at=activated_at,
            last_reported_at=now,
        )
        db.add(active)

    elif active.artifact_id == artifact.id:
        result = "already_active"
        active_revision = active.active_revision
        activated_at = active.activated_at
        active.activation_request_id = body.request_id
        active.last_reported_at = now

    else:
        result = "activated"
        active.artifact_id = artifact.id
        active.active_revision += 1
        active.activation_request_id = body.request_id
        active.activated_at = now
        active.last_reported_at = now

        active_revision = active.active_revision
        activated_at = now

    activation_request = MapActivationRequest(
        product_type=product_type,
        device_id=device_id,
        request_id=body.request_id,
        map_id=body.map_id,
        map_version=body.map_version,
        checksum=body.checksum,
        result=result,
        active_revision=active_revision,
        activated_at=activated_at,
    )

    db.add(activation_request)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _activation_response(
        result=result,
        device_id=device_id,
        active_revision=active_revision,
        map_id=body.map_id,
        map_version=body.map_version,
        checksum=body.checksum,
        activated_at=activated_at,
    )
