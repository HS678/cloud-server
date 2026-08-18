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

机器人地图链路：

Robot
    ->
POST /api/maps/upload
    ->
Cloud Server
    ->
/opt/cloud-server/storage/maps

Robot
    ->
PUT /api/devices/{productType}/{deviceId}/active-map
    ->
PostgreSQL current map state

Android APP
    ->
GET current / metadata / content
    ->
Cloud Server

## HTTP Service

HTTP 服务由：

- Nginx
- FastAPI
- PostgreSQL

组成。

HTTP Compose：

/opt/cloud-server/deploy/docker-compose.yml

FastAPI 端口 8000 和 PostgreSQL 端口 5432 当前仅在 Docker 网络内部使用。

公网 HTTP 入口为：

- port 80

HTTPS 443 尚未启用。

## MQTT Service

MQTT Broker：

- EMQX 5.8.6

MQTT 使用独立 Compose：

/opt/cloud-server/mqtt/docker-compose.yml

Container：

- robot-emqx

当前：

- MQTT TCP: 1883
- Dashboard: 18083

生产阶段计划迁移到：

- MQTTS: 8883

## Map V2 Persistence

PostgreSQL Map V2 表：

- map_artifacts
- device_active_maps
- map_activation_requests

关系：

MapArtifact
    ->
immutable map version

DeviceActiveMap
    ->
device current active artifact

MapActivationRequest
    ->
Robot active-map idempotency record

地图文件存储：

/opt/cloud-server/storage/maps/{productType}/{deviceId}/{mapId}/{mapVersion}/map.json

核心原则：

- Upload 不改变 current。
- active-map 才改变 current。
- exact map content 是不可变资源。
- current 是可变指针。

## MQTT Pose and HTTP Map Boundary

当前第二版地图同步设计：

- 地图文件和 current map 通过 HTTP。
- MQTT 不再作为地图文件来源。
- pose 继续通过 MQTT 实时传输。
- pose 包含 mapId 和 mapVersion。
- APP 只有在 pose.mapId + pose.mapVersion 与当前已加载地图一致时才绘制位置。

当前 pose topic：

device/{productType}/{deviceId}/pose

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

当前 APP 与 Robot MQTT 协议应继续视为稳定边界。

没有确认协议缺陷时，不修改：

- MQTT Topic
- MQTT payload
- Robot 控制命令格式
- Robot 当前 MQTT 接口行为

Map V2 改造仅改变地图同步来源：

- map：HTTP
- pose：MQTT

## Source of Truth

当前服务器实际部署状态以：

docs/current_environment.md

为准。
