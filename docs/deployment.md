# Cloud Server Deployment

## Deployment Root

/opt/cloud-server

HTTP 服务 Compose：

/opt/cloud-server/deploy/docker-compose.yml

MQTT 服务 Compose：

/opt/cloud-server/mqtt/docker-compose.yml

HTTP 与 MQTT 为独立 Docker Compose，不应合并启动。

## HTTP Service

运行 HTTP 服务相关 Docker Compose 命令时：

cd /opt/cloud-server/deploy

当前服务：

- vgsolar-nginx
- vgsolar-api
- vgsolar-postgres

常用检查：

docker compose ps
curl http://127.0.0.1/health

## MQTT Service

运行 MQTT 服务相关 Docker Compose 命令时：

cd /opt/cloud-server/mqtt

当前服务：

- robot-emqx

MQTT 持久化数据：

/opt/cloud-server/data/emqx

MQTT 日志：

/opt/cloud-server/logs/emqx

## Current Ports

External:

- 22 SSH
- 80 HTTP
- 1883 MQTT
- 18083 EMQX Dashboard

Internal:

- 8000 FastAPI
- 5432 PostgreSQL

## Database Migration

Alembic 配置：

/opt/cloud-server/services/api/alembic.ini

Migration files：

/opt/cloud-server/services/api/alembic/versions

当前 revision：

0003_map_artifact_v2

Migration chain：

0001_baseline_existing
    ->
0002_app_platform_v1
    ->
0003_map_artifact_v2

Map V2 数据表：

- map_artifacts
- device_active_maps
- map_activation_requests

Map V2 migration 已经应用到当前真实 PostgreSQL。

## Map Storage

地图文件根目录：

/opt/cloud-server/storage/maps

Map V2 路径：

/opt/cloud-server/storage/maps/{productType}/{deviceId}/{mapId}/{mapVersion}/map.json

地图文件属于持久化业务数据，不随 API 容器生命周期删除。

## Environment Variables

HTTP 服务环境变量：

/opt/cloud-server/deploy/.env

MQTT Compose 环境变量：

/opt/cloud-server/mqtt/.env

不要将 .env 内容复制到 Git、项目文档或公开日志。

当前开发环境中仍存在长期 MQTT 凭据，生产前需要迁移到动态凭据和设备级 ACL。

## Build and Deploy API

API 代码修改后：

cd /opt/cloud-server/deploy

docker compose build api
docker compose up -d --no-deps api

确认：

docker compose ps api
curl http://127.0.0.1/health

## Current Environment

执行任何部署修改前先阅读：

docs/current_environment.md

## Disaster Recovery

改造前恢复点：

/opt/cloud-server/backups

baseline：

20260817_174934

Map V2 migration 前额外 PostgreSQL backup：

pre_map_v2_20260818.sql

这些灾难恢复文件不得作为普通临时文件清理。
