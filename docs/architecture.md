# Cloud Server Architecture

## Current Architecture

当前光伏机器人平台由 Android APP、Cloud Server 和 Robot 三部分组成。

HTTP 业务链路：

Android APP
    ->
Nginx :80
    ->
FastAPI
    ->
PostgreSQL

机器人实时通信链路：

Android APP
    ->
EMQX :1883
    ->
Robot

机器人地图上传：

Robot
    ->
HTTP Upload
    ->
Cloud Server
    ->
/opt/cloud-server/storage/maps

## HTTP Service

HTTP 服务由：

- Nginx
- FastAPI
- PostgreSQL

组成。

FastAPI 端口 8000 和 PostgreSQL 端口 5432 当前仅在 Docker 网络内部使用。

公网 HTTP 入口为：

- port 80

HTTPS 443 尚未启用。

## MQTT Service

MQTT Broker：

- EMQX

当前：

- MQTT TCP: 1883
- Dashboard: 18083

生产阶段计划迁移到：

- MQTTS: 8883

## Authentication

HTTP API 当前使用：

- Access Token: JWT / HS256
- Refresh Token: opaque random token
- PostgreSQL sessions 表保存 Refresh Token hash

详细策略见：

docs/current_environment.md

## Device Authorization

用户和机器人通过：

user_device_bindings

建立多对多绑定。

角色：

- admin
- operator
- viewer

设备列表 API 同时返回 role 和 permissions。

## Protocol Boundary

当前 APP 与 Robot MQTT 联调已经验证。

没有确认协议缺陷时，不修改：

- MQTT Topic
- MQTT payload
- Robot 控制命令格式
- Robot 当前 MQTT 接口行为

## Source of Truth

当前服务器实际部署状态以：

docs/current_environment.md

为准。
