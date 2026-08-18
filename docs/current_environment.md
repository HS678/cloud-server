# Cloud Server Current Environment

Last verified: 2026-08-17

## 1. Deployment

Project root:

/opt/cloud-server

Production Docker Compose:

/opt/cloud-server/deploy/docker-compose.yml

Run Docker Compose commands from:

/opt/cloud-server/deploy

Main services:

- vgsolar-nginx
- vgsolar-api
- vgsolar-postgres
- robot-emqx

External ports:

- 22: SSH
- 80: HTTP
- 1883: MQTT
- 18083: EMQX Dashboard

Internal-only service ports:

- 8000: FastAPI
- 5432: PostgreSQL

HTTPS 443 and MQTTS 8883 are not enabled yet.

## 2. Database

Database:

- PostgreSQL 16
- database: vgsolar
- current Alembic revision: 0002_app_platform_v1

Migration chain:

- 0001_baseline_existing
- 0002_app_platform_v1

The migration chain has been verified against a completely empty temporary
database and successfully rebuilds the current seven-table schema.

Core tables:

- users
- devices
- user_device_bindings
- sessions
- job_records
- firmware_meta
- alembic_version

## 3. HTTP Authentication

Authentication endpoints:

- POST /api/auth/login
- POST /api/auth/refresh
- POST /api/auth/logout
- GET /api/users/me

Access Token:

- JWT
- algorithm: HS256
- lifetime: 60 minutes

Refresh Token:

- opaque random token
- lifetime: 30 days
- only SHA-256 hash is stored in PostgreSQL
- refresh token rotation is enabled

Refresh flow:

- login returns access_token + refresh_token
- refresh returns a new access_token + new refresh_token
- the previous refresh_token becomes invalid immediately
- logout revokes the current refresh-token session

User status:

- active
- disabled

A disabled user cannot:

- log in
- continue using an already issued Access Token

## 4. Session Policy

Current settings:

- MAX_ACTIVE_SESSIONS_PER_USER=5
- SESSION_RETENTION_DAYS=30

Behavior:

- one user may have up to 5 active sessions
- multiple Android devices may remain logged in simultaneously
- when a sixth session is created, the oldest active session is revoked
- expired and revoked sessions are retained for 30 days
- old terminal sessions are cleaned during later login/session maintenance

The complete session lifecycle has been tested:

- login
- refresh
- refresh-token rotation
- old refresh-token rejection
- logout
- revoked refresh-token rejection
- maximum active session enforcement
- retention cleanup

## 5. Device Binding and Permissions

User/device relationships are stored in:

- user_device_bindings

Relationship model:

- one user can manage multiple robots
- one robot can be bound to multiple users

Supported roles:

- admin
- operator
- viewer

Permissions:

admin:
- view: true
- control: true
- configure: true
- upgrade: true

operator:
- view: true
- control: true
- configure: false
- upgrade: false

viewer:
- view: true
- control: false
- configure: false
- upgrade: false

GET /api/devices currently returns:

- device_id
- display_name
- role
- permissions

Current test bindings:

- test@vgsolar.com -> rk3588 -> admin
- test@vgsolar.com -> crawler_00000001 -> admin

Wi-Fi modification requires admin.

Firmware upgrade requires admin.

Firmware metadata lookup is isolated per device.
If a device has no firmware metadata, the API returns HTTP 404 instead of
falling back to firmware belonging to another device.

## 6. MQTT and Map

Current MQTT broker:

- EMQX
- TCP MQTT port: 1883
- EMQX Dashboard port: 18083

Current robot MQTT communication has already been tested and should be treated
as a stable protocol boundary during the current APP/cloud refactor.

Do not change without a confirmed protocol defect:

- MQTT topics
- MQTT payload formats
- robot control command formats
- current robot MQTT interface behavior

Current test environment has:

- one robot MQTT credential
- one APP MQTT credential

Production follow-up:

- migrate MQTT 1883 to MQTTS 8883
- issue short-lived APP MQTT credentials from the cloud
- use per-device robot credentials and ACL
- restrict public access to EMQX Dashboard

Map storage root:

/opt/cloud-server/storage/maps

Current crawler map path:

/opt/cloud-server/storage/maps/crawler/crawler_00000001

The existing map upload API and robot map interaction should remain unchanged
unless a real defect is identified.

## 7. Disaster Recovery Baseline

A full pre-refactor recovery baseline was created before the current cloud
changes.

Baseline timestamp:

20260817_174934

Location:

/opt/cloud-server/backups

Files:

- cloud_config_20260817_174934.tar.gz
- emqx_20260817_174934.tar.gz
- postgres_20260817_174934.sql
- storage_20260817_174934.tar.gz

These four files are the primary disaster recovery point and must not be
deleted during routine cleanup.

The baseline archives and PostgreSQL dump were already integrity checked.

## 8. Current Project State

Completed and verified:

- Alembic migration foundation
- fresh empty-database migration test
- user active/disabled status
- user-device many-to-many bindings
- admin/operator/viewer roles
- device permissions response
- Access Token authentication
- Refresh Token persistence
- Refresh Token rotation
- logout/revoke
- maximum 5 active sessions per user
- 30-day revoked/expired session retention cleanup
- firmware metadata device isolation

Current HTTP/API phase is considered functionally complete for Android auth
integration.

Next primary phase:

Android APP Session/Auth adaptation

Android work will include:

- persist Access Token
- persist Refresh Token
- global Bearer token injection
- refresh once after HTTP 401
- retry the original request after successful refresh
- force logout when refresh fails
- integrate GET /api/users/me
- integrate role and permissions from GET /api/devices
- correct Android navigation/back-stack behavior

## 9. Production Follow-up

The current environment is still a development/integration deployment.

Before production release:

- enable HTTPS 443
- enable MQTTS 8883
- restrict EMQX Dashboard 18083
- implement MQTT dynamic authentication and ACL
- remove long-lived MQTT secrets from the Android APP
- review/remove bootstrap behavior
- tighten CORS
- expand automated API tests
- establish PostgreSQL backup policy
- configure log rotation
- add monitoring and alerting
