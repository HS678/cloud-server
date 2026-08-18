# Cloud Server Current Environment

Last verified: 2026-08-18

## 1. Deployment

Project root:

/opt/cloud-server

HTTP Docker Compose:

/opt/cloud-server/deploy/docker-compose.yml

MQTT Docker Compose:

/opt/cloud-server/mqtt/docker-compose.yml

Run HTTP Docker Compose commands from:

/opt/cloud-server/deploy

Run MQTT Docker Compose commands from:

/opt/cloud-server/mqtt

HTTP services:

- vgsolar-nginx
- vgsolar-api
- vgsolar-postgres

MQTT service:

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
- current Alembic revision: 0003_map_artifact_v2

Migration chain:

- 0001_baseline_existing
- 0002_app_platform_v1
- 0003_map_artifact_v2

Core existing tables:

- users
- devices
- user_device_bindings
- sessions
- job_records
- firmware_meta
- alembic_version

Map V2 tables:

- map_artifacts
- device_active_maps
- map_activation_requests

Map V2 migration was applied successfully to the real PostgreSQL deployment.

Before the Map V2 migration, a PostgreSQL backup was created:

/opt/cloud-server/backups/pre_map_v2_20260818.sql

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

Current test bindings include:

- test@vgsolar.com -> rk3588 -> admin
- test@vgsolar.com -> crawler_00000001 -> admin

Wi-Fi modification requires admin.

Firmware upgrade requires admin.

Firmware metadata lookup is isolated per device.

## 6. Map V2

Map storage root:

/opt/cloud-server/storage/maps

Storage layout:

/opt/cloud-server/storage/maps/{productType}/{deviceId}/{mapId}/{mapVersion}/map.json

Current crawler test data includes:

- crawler_00000001 / map 320 / version 1
- crawler_00000001 / map 320 / version 2

Robot APIs:

- POST /api/maps/upload
- PUT /api/devices/{productType}/{deviceId}/active-map

APP APIs:

- GET /api/devices/{productType}/{deviceId}/maps/current
- GET /api/devices/{productType}/{deviceId}/maps/{mapId}/versions/{mapVersion}
- GET /api/devices/{productType}/{deviceId}/maps/{mapId}/versions/{mapVersion}/content

Core behavior:

- uploading a map artifact does not change device current map
- only active-map changes current map
- activeRevision increments only when the active artifact changes
- repeated upload of identical identity/checksum returns already_exists
- repeated active-map requestId returns the original idempotent result
- same active artifact with a new requestId returns already_active
- map content is returned as original uploaded JSON bytes
- exact map content uses ETag and immutable caching
- current endpoint uses Cache-Control: no-store

Real integration verification:

1. uploaded map 320/1 -> HTTP 201 created
2. activated 320/1 -> activeRevision 1
3. replayed same requestId -> same activated result, revision unchanged
4. new requestId for 320/1 -> already_active, revision unchanged
5. uploaded 320/2 without activation -> current remained 320/1
6. activated 320/2 -> activeRevision 2
7. APP current returned map 320/2
8. APP metadata returned map 320/2 READY
9. APP content returned original 118-byte JSON
10. If-None-Match returned HTTP 304

Current real active map for crawler_00000001 after integration test:

- mapId: 320
- mapVersion: 2
- activeRevision: 2

## 7. MQTT

Current MQTT broker:

- EMQX 5.8.6
- container: robot-emqx
- TCP MQTT port: 1883
- EMQX Dashboard port: 18083

MQTT persistent data:

/opt/cloud-server/data/emqx

MQTT logs:

/opt/cloud-server/logs/emqx

Current test environment has:

- one Robot MQTT credential
- one APP MQTT credential

Credentials are not documented in Git-tracked files.

Current pose topic:

device/{productType}/{deviceId}/pose

Pose base fields:

- version
- deviceId
- productType
- timestamp

Pose map/location fields:

- mapId
- mapVersion
- blockId
- cellId
- cellRow
- cellCol
- innerRow
- innerCol
- headingCode
- heading

APP should validate:

- version == "1.0"
- productType matches current device
- deviceId matches current device
- pose.mapId + pose.mapVersion matches the currently loaded HTTP map before drawing

Real MQTT verification completed:

- Robot credential successfully published QoS 1 pose
- APP credential successfully subscribed to pose
- topic: device/crawler/crawler_00000001/pose
- published pose used mapId=320 and mapVersion=2
- APP-side subscriber received the complete payload

Map V2 design boundary:

- map files/current state: HTTP
- live pose: MQTT
- old MQTT map/mapJsonUrl should not be used as the APP map source

Do not change existing MQTT topics, control payloads, or Robot command behavior without a confirmed protocol defect.

## 8. Disaster Recovery Baseline

A full pre-refactor recovery baseline exists.

Baseline timestamp:

20260817_174934

Location:

/opt/cloud-server/backups

Files:

- cloud_config_20260817_174934.tar.gz
- emqx_20260817_174934.tar.gz
- postgres_20260817_174934.sql
- storage_20260817_174934.tar.gz

These four files are the primary disaster recovery point and must not be deleted during routine cleanup.

The baseline archives and PostgreSQL dump were already integrity checked.

Additional Map V2 pre-migration backup:

- pre_map_v2_20260818.sql

## 9. Current Project State

Completed and verified:

- Alembic migration foundation
- user active/disabled status
- user-device many-to-many bindings
- admin/operator/viewer roles
- device permissions response
- Access Token authentication
- Refresh Token persistence and rotation
- logout/revoke
- maximum active session enforcement
- session retention cleanup
- firmware metadata device isolation
- Map V2 persistence schema
- Map V2 Robot artifact upload
- Map V2 Robot active-map activation
- Map V2 APP current/metadata/content APIs
- real PostgreSQL Map V2 integration
- raw map file storage
- ETag / 304 behavior
- MQTT pose Robot publish / APP subscribe verification
- pose mapId/mapVersion aligned with active HTTP map

Cloud Map V2 server-side main chain is considered functionally verified.

Next primary phase:

Android APP Map V2 adaptation.

Android work should include:

- stop using MQTT map/mapJsonUrl as map source
- obtain current map via HTTP
- download exact content via HTTP
- cache map by productType/deviceId/mapId/mapVersion/checksum
- compare incoming pose.mapId/mapVersion with currently loaded map
- trigger map synchronization when pose references another active map
- preserve existing MQTT control/status behavior

## 10. Production Follow-up

The current environment is still a development/integration deployment.

Before production release:

- enable HTTPS 443
- enable MQTTS 8883
- restrict EMQX Dashboard 18083
- implement MQTT dynamic authentication and ACL
- use per-device Robot credentials
- remove long-lived MQTT secrets from the Android APP
- review/remove bootstrap behavior
- tighten CORS
- expand automated API tests
- add concurrency tests for active-map races
- establish PostgreSQL backup policy
- configure log rotation
- add monitoring and alerting
