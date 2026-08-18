# Server Migration History

Status:

COMPLETED

Migration completed:

2026-08-08

## Old Environment

/opt/robot-platform

## Current Environment

/opt/cloud-server

## Migration Goal

使用 /opt/cloud-server 替代旧 robot-platform 云服务，同时保持已经验证的 APP 和 Robot 通信协议兼容。

## Migration Requirements

迁移期间要求：

- APP 原有 MQTT 机器人控制协议保持兼容
- Robot 原有 MQTT 协议保持兼容
- API 保持兼容
- MQTT Topic 保持兼容
- MQTT payload 保持兼容
- 地图数据正常迁移

## Migrated Services

HTTP:

- Nginx
- FastAPI
- PostgreSQL

MQTT:

- EMQX

当前实际部署结构：

HTTP:

/opt/cloud-server/deploy/docker-compose.yml

MQTT:

/opt/cloud-server/mqtt/docker-compose.yml

两套 Compose 独立维护。

## Post-Migration Map V2 Evolution

迁移完成后，cloud-server 已继续演进到 Map V2：

- 新增 map_artifacts
- 新增 device_active_maps
- 新增 map_activation_requests
- Robot 地图上传改为不可变 artifact
- Robot active-map 成为 current map 唯一切换来源
- APP current/metadata/content 改为 HTTP
- APP 地图文件不再依赖 MQTT mapJsonUrl
- MQTT pose 继续保留并携带 mapId/mapVersion

该 Map V2 改造保持原有 MQTT 控制/status 协议边界，不修改既有机器人控制接口。

## Verification

已验证：

- API health check
- 用户登录
- Nginx API proxy
- PostgreSQL connection
- APP/Robot MQTT credential authentication
- Robot MQTT pose publish
- APP MQTT pose subscribe
- Map V2 Robot upload
- Map V2 Robot active-map
- upload 不改变 current
- activeRevision 增长和幂等
- APP current
- APP metadata
- APP exact content
- ETag / HTTP 304
- pose mapId/mapVersion 与 HTTP current map 对齐

## Historical Source

旧 `/opt/robot-platform` 当前只作为历史资料来源。

如果需要确认旧 MQTT Topic/payload，应只读查阅历史文档和模拟器，不应把旧目录重新作为生产运行目录。

## Result

cloud-server 已成功替代旧 robot-platform 云服务。

当前正式维护目录：

/opt/cloud-server

该文档仅作为历史迁移记录。

后续配置和运维不得再以旧目录作为当前环境依据。

当前环境请阅读：

docs/current_environment.md
