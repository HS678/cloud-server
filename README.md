# Robot Cloud Server

光伏机器人云平台服务端根目录。

当前正式云服务统一维护在：

/opt/cloud-server

## Directory Structure

- backups/：灾难恢复备份
- config/：公共配置
- data/：服务持久化数据
- deploy/：HTTP 服务 Docker Compose、Nginx、PostgreSQL、FastAPI
- docs/：架构、接口、部署、迁移、当前环境文档
- logs/：服务日志
- mqtt/：独立 EMQX MQTT Broker Docker Compose
- scripts/：运维脚本
- services/：云端业务服务代码
- storage/：地图、OTA 和其他机器人业务文件

## Current Services

HTTP:

- Nginx
- FastAPI
- PostgreSQL

MQTT:

- EMQX

HTTP 与 MQTT 使用独立 Docker Compose：

- /opt/cloud-server/deploy/docker-compose.yml
- /opt/cloud-server/mqtt/docker-compose.yml

两套服务通过外部 Docker network 进行隔离和协作。

## Current Map V2

Map V2 当前已实现并完成真实联调。

Robot:

- POST /api/maps/upload
- PUT /api/devices/{productType}/{deviceId}/active-map

APP:

- GET /api/devices/{productType}/{deviceId}/maps/current
- GET /api/devices/{productType}/{deviceId}/maps/{mapId}/versions/{mapVersion}
- GET /api/devices/{productType}/{deviceId}/maps/{mapId}/versions/{mapVersion}/content

核心规则：

- 上传地图不会自动改变 current map。
- 只有 Robot active-map 上报会改变 current map。
- activeRevision 仅在实际切换地图时递增。
- 地图文件按原始 JSON map 字节保存。
- APP 地图通过 HTTP 获取，不再依赖 MQTT mapJsonUrl。
- MQTT pose 继续用于实时位置，并携带 mapId/mapVersion。

## Documentation

修改服务器配置前，首先阅读：

- docs/current_environment.md

其他文档：

- docs/architecture.md：当前云平台架构
- docs/api.md：当前 HTTP API
- docs/deployment.md：部署和运行方式
- docs/mqtt.md：MQTT 当前状态和协议边界
- docs/migration.md：从旧环境迁移到 cloud-server 的历史记录

## Deployment Principle

1. 云服务目录与客户端代码分离。
2. APP 和机器人已验证的 MQTT 协议保持稳定。
3. HTTP 与 MQTT 服务独立部署。
4. 服务配置与业务代码分离。
5. 持久化数据与容器生命周期分离。
6. 数据库结构通过 Alembic 管理。
7. 支持服务器迁移和灾难恢复。

## Recovery Baseline

改造前灾难恢复点位于：

/opt/cloud-server/backups

当前必须保留的基线：

20260817_174934

详细信息见：

docs/current_environment.md
