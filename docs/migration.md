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

- APP 无需修改原有 MQTT 机器人协议
- Robot 无需修改原有 MQTT 协议
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

## Verification

已验证：

- API health check
- 用户登录
- Nginx API proxy
- PostgreSQL connection
- 地图静态下载
- APP MQTT connection
- Robot MQTT connection
- MQTT Topic communication

## Result

cloud-server 已成功替代旧 robot-platform 云服务。

当前正式维护目录：

/opt/cloud-server

该文档仅作为历史迁移记录。

后续配置和运维不得再以旧目录作为当前环境依据。

当前环境请阅读：

docs/current_environment.md
