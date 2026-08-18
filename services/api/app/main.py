"""光伏机器人 HTTP API 最小联调骨架。"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import BaseSettings
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.database import Base, SessionLocal, get_db
from app.map_upload import router as map_upload_router

ALGORITHM = "HS256"


class Settings(BaseSettings):
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    postgres_user: str = Field(default="vgsolar", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="vgsolar", alias="POSTGRES_DB")
    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    jwt_secret: str = Field(alias="JWT_SECRET")
    access_token_expire_minutes: int = Field(
        default=60,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
        ge=1,
    )
    refresh_token_expire_days: int = Field(
        default=30,
        alias="REFRESH_TOKEN_EXPIRE_DAYS",
        ge=1,
    )
    max_active_sessions_per_user: int = Field(
        default=5,
        alias="MAX_ACTIVE_SESSIONS_PER_USER",
        ge=1,
    )
    session_retention_days: int = Field(
        default=30,
        alias="SESSION_RETENTION_DAYS",
        ge=1,
    )
    bootstrap_email: EmailStr = Field(alias="API_BOOTSTRAP_EMAIL")
    bootstrap_password: str = Field(alias="API_BOOTSTRAP_PASSWORD")
    public_host: str = Field(default="localhost", alias="PUBLIC_HOST")



settings = Settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product_type: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(128))
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    wifi_ssid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wifi_password: Mapped[str | None] = mapped_column(String(128), nullable=True)

    owner: Mapped[User] = relationship()


class UserDeviceBinding(Base):
    __tablename__ = "user_device_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    refresh_token_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class JobRecord(Base):
    __tablename__ = "job_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    cleaned_rows: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class FirmwareMeta(Base):
    __tablename__ = "firmware_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_model: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    download_url: Mapped[str] = mapped_column(String(512))
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class DevicePermissions(BaseModel):
    view: bool
    control: bool
    configure: bool
    upgrade: bool


class DeviceResponse(BaseModel):
    device_id: str
    display_name: str
    role: str
    permissions: DevicePermissions


class UserMeResponse(BaseModel):
    id: int
    email: EmailStr
    display_name: str | None
    status: str


class JobResponse(BaseModel):
    id: int
    device_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    cleaned_rows: int
    note: str | None


class FirmwareResponse(BaseModel):
    version: str
    download_url: str
    release_notes: str | None
    published_at: datetime


class WifiConfigResponse(BaseModel):
    device_id: str
    ssid: str | None
    configured: bool


class WifiConfigUpdate(BaseModel):
    ssid: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class FirmwareUpgradeRequest(BaseModel):
    device_id: str
    target_version: str | None = None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def maintain_user_sessions(
    db: Session,
    user_id: int,
) -> None:
    now = datetime.now(timezone.utc)

    active_sessions = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.status == "active",
        )
        .order_by(UserSession.created_at.desc())
    ).all()

    valid_active_sessions: list[UserSession] = []

    for session in active_sessions:
        if session.expires_at <= now:
            session.status = "expired"
        else:
            valid_active_sessions.append(session)

    keep_count = max(settings.max_active_sessions_per_user - 1, 0)

    for session in valid_active_sessions[keep_count:]:
        session.status = "revoked"
        session.revoked_at = now

    retention_cutoff = now - timedelta(
        days=settings.session_retention_days
    )

    terminal_sessions = db.scalars(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.status.in_(["revoked", "expired"]),
        )
    ).all()

    for session in terminal_sessions:
        reference_time = session.revoked_at or session.expires_at
        if reference_time < retention_cutoff:
            db.delete(session)


def create_refresh_session(
    db: Session,
    user_id: int,
) -> tuple[UserSession, str]:
    now = datetime.now(timezone.utc)
    refresh_token = secrets.token_urlsafe(48)

    session = UserSession(
        id=uuid.uuid4().hex,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        status="active",
        created_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )

    db.add(session)

    return session, refresh_token


def issue_token_pair(
    db: Session,
    user: User,
) -> TokenResponse:
    maintain_user_sessions(db, user.id)

    session, refresh_token = create_refresh_session(db, user.id)

    access_token = create_access_token(user.id, user.email)

    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        refresh_expires_in=settings.refresh_token_expire_days * 86400,
    )


def bootstrap_data(db: Session) -> None:
    user = db.scalar(select(User).where(User.email == settings.bootstrap_email))
    if user is None:
        user = User(
            email=settings.bootstrap_email,
            password_hash=hash_password(settings.bootstrap_password),
        )
        db.add(user)
        db.flush()

    device = db.scalar(select(Device).where(Device.device_id == "rk3588"))
    if device is None:
        db.add(
            Device(
                device_id="rk3588",
                display_name="Kwun-B22L-180926",
                owner_user_id=user.id,
                wifi_ssid="Robot-AP",
                wifi_password="robot123456",
            )
        )

    if db.scalar(select(JobRecord).limit(1)) is None:
        now = datetime.now(timezone.utc)
        db.add(
            JobRecord(
                device_id="rk3588",
                started_at=now - timedelta(hours=2),
                finished_at=now - timedelta(hours=1),
                status="completed",
                cleaned_rows=12,
                note="联调示例作业记录",
            )
        )

    if db.scalar(select(FirmwareMeta).limit(1)) is None:
        db.add(
            FirmwareMeta(
                device_model="rk3588",
                version="1.0.0",
                download_url=f"http://{settings.public_host}/api/firmware/download/rk3588-1.0.0.bin",
                release_notes="联调占位固件包",
                published_at=datetime.now(timezone.utc),
            )
        )

    db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        bootstrap_data(db)
    yield


app = FastAPI(title="VGSolar Robot API", version="0.1.0", lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path == "/api/maps/upload":
        return JSONResponse(status_code=400, content={"detail": jsonable_encoder(exc.errors())})
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


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


app.include_router(map_upload_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或 Token 无效")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 解析失败") from exc

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被停用",
        )

    return user


def get_device_access(
    db: Session,
    user_id: int,
    device_id: str,
) -> tuple[Device, UserDeviceBinding] | None:
    row = db.execute(
        select(Device, UserDeviceBinding)
        .join(
            UserDeviceBinding,
            UserDeviceBinding.device_id == Device.id,
        )
        .where(
            UserDeviceBinding.user_id == user_id,
            Device.device_id == device_id,
        )
    ).first()

    if row is None:
        return None

    return row[0], row[1]


def require_device_access(
    db: Session,
    user_id: int,
    device_id: str,
    allowed_roles: set[str] | None = None,
) -> tuple[Device, UserDeviceBinding]:
    access = get_device_access(db, user_id, device_id)

    if access is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="设备不存在或无权限",
        )

    device, binding = access

    if allowed_roles is not None and binding.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前设备角色无权执行此操作",
        )

    return device, binding


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被停用",
        )

    user.last_login_at = datetime.now(timezone.utc)

    return issue_token_pair(db, user)


@app.post("/api/auth/refresh", response_model=TokenResponse)
def refresh_access_token(
    body: RefreshTokenRequest,
    db: Annotated[Session, Depends(get_db)],
):
    now = datetime.now(timezone.utc)
    token_hash = hash_refresh_token(body.refresh_token)

    session = db.scalar(
        select(UserSession).where(
            UserSession.refresh_token_hash == token_hash,
        )
    )

    if session is None or session.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 无效",
        )

    if session.expires_at <= now:
        session.status = "expired"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 已过期",
        )

    user = db.get(User, session.user_id)

    if user is None:
        session.status = "revoked"
        session.revoked_at = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if user.status != "active":
        session.status = "revoked"
        session.revoked_at = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被停用",
        )

    new_refresh_token = secrets.token_urlsafe(48)

    session.refresh_token_hash = hash_refresh_token(new_refresh_token)
    session.last_used_at = now
    session.expires_at = now + timedelta(
        days=settings.refresh_token_expire_days
    )

    access_token = create_access_token(user.id, user.email)

    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        refresh_expires_in=settings.refresh_token_expire_days * 86400,
    )


@app.post("/api/auth/logout")
def logout(
    body: LogoutRequest,
    db: Annotated[Session, Depends(get_db)],
):
    token_hash = hash_refresh_token(body.refresh_token)

    session = db.scalar(
        select(UserSession).where(
            UserSession.refresh_token_hash == token_hash,
        )
    )

    if session is not None and session.status == "active":
        session.status = "revoked"
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()

    return {"status": "ok"}


@app.get("/api/users/me", response_model=UserMeResponse)
def get_me(
    user: Annotated[User, Depends(get_current_user)],
):
    return UserMeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
    )


def permissions_for_role(role: str) -> DevicePermissions:
    if role == "admin":
        return DevicePermissions(
            view=True,
            control=True,
            configure=True,
            upgrade=True,
        )

    if role == "operator":
        return DevicePermissions(
            view=True,
            control=True,
            configure=False,
            upgrade=False,
        )

    return DevicePermissions(
        view=True,
        control=False,
        configure=False,
        upgrade=False,
    )


@app.get("/api/devices", response_model=list[DeviceResponse])
def list_devices(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    rows = db.execute(
        select(Device, UserDeviceBinding)
        .join(
            UserDeviceBinding,
            UserDeviceBinding.device_id == Device.id,
        )
        .where(UserDeviceBinding.user_id == user.id)
        .order_by(Device.id)
    ).all()

    return [
        DeviceResponse(
            device_id=device.device_id,
            display_name=device.display_name,
            role=binding.role,
            permissions=permissions_for_role(binding.role),
        )
        for device, binding in rows
    ]


@app.get("/api/jobs", response_model=list[JobResponse])
def list_jobs(
    device_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    device, _binding = require_device_access(
        db,
        user.id,
        device_id,
    )

    jobs = db.scalars(
        select(JobRecord).where(JobRecord.device_id == device_id).order_by(JobRecord.started_at.desc())
    ).all()
    return [
        JobResponse(
            id=j.id,
            device_id=j.device_id,
            started_at=j.started_at,
            finished_at=j.finished_at,
            status=j.status,
            cleaned_rows=j.cleaned_rows,
            note=j.note,
        )
        for j in jobs
    ]


@app.get("/api/firmware/latest", response_model=FirmwareResponse)
def latest_firmware(
    device_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    device, _binding = require_device_access(
        db,
        user.id,
        device_id,
    )

    meta = db.scalar(
        select(FirmwareMeta)
        .where(FirmwareMeta.device_model == device.device_id)
        .order_by(FirmwareMeta.published_at.desc())
    )
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该设备暂无固件信息",
        )

    return FirmwareResponse(
        version=meta.version,
        download_url=meta.download_url,
        release_notes=meta.release_notes,
        published_at=meta.published_at,
    )


@app.post("/api/firmware/upgrade")
def trigger_firmware_upgrade(
    body: FirmwareUpgradeRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    device, _binding = require_device_access(
        db,
        user.id,
        body.device_id,
        allowed_roles={"admin"},
    )

    return {
        "status": "accepted",
        "device_id": body.device_id,
        "message": "固件升级任务已受理（联调占位接口，需硬件侧 OTA 对接）",
        "target_version": body.target_version,
    }


@app.get("/api/devices/{device_id}/wifi", response_model=WifiConfigResponse)
def get_wifi_config(
    device_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    device, _binding = require_device_access(
        db,
        user.id,
        device_id,
    )

    return WifiConfigResponse(
        device_id=device.device_id,
        ssid=device.wifi_ssid,
        configured=bool(device.wifi_ssid),
    )


@app.put("/api/devices/{device_id}/wifi", response_model=WifiConfigResponse)
def update_wifi_config(
    device_id: str,
    body: WifiConfigUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    device, _binding = require_device_access(
        db,
        user.id,
        device_id,
        allowed_roles={"admin"},
    )

    device.wifi_ssid = body.ssid
    device.wifi_password = body.password
    db.commit()
    db.refresh(device)

    return WifiConfigResponse(
        device_id=device.device_id,
        ssid=device.wifi_ssid,
        configured=True,
    )
