# MQTT Environment

## Broker

当前 MQTT Broker：

EMQX

Container：

robot-emqx

Current version:

5.8.6

MQTT Compose：

/opt/cloud-server/mqtt/docker-compose.yml

## Ports

Current MQTT:

1883

Current EMQX Dashboard:

18083

Future production MQTTS:

8883

## Persistent Data

EMQX data:

/opt/cloud-server/data/emqx

EMQX logs:

/opt/cloud-server/logs/emqx

## Current Credentials

当前联调环境已经分别创建：

- Robot MQTT credential
- APP MQTT credential

具体用户名和密码不记录在本文档。

Robot 与 APP 使用独立账号。

## Pose Topic

当前 pose topic：

device/{productType}/{deviceId}/pose

当前 crawler 测试设备：

device/crawler/crawler_00000001/pose

QoS：

1

Pose 公共字段：

- version
- deviceId
- productType
- timestamp

Pose 地图和位置字段：

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

当前协议要求：

- version == "1.0"
- productType 与当前设备一致
- deviceId 与当前设备一致
- pose.mapId + pose.mapVersion 必须与 APP 当前加载地图一致后才参与绘制

## Map V2 Boundary

第二版地图同步中：

地图文件和 current map：

- HTTP

机器人实时 pose：

- MQTT

因此 APP 不应再把 MQTT map/mapJsonUrl 作为地图文件来源。

历史 MQTT map topic 可能继续存在于旧模拟器/兼容环境中，但 Map V2 APP 不应依赖它。

## Verified MQTT Integration

2026-08-18 实际验证：

Robot 账号向：

device/crawler/crawler_00000001/pose

发布 QoS 1 pose。

APP 账号成功订阅并收到完整 JSON。

测试 payload 使用：

- mapId: 320
- mapVersion: 2

该版本与 Cloud current map 一致。

## Protocol Stability

当前 Robot 与 APP MQTT 通信协议继续视为稳定边界。

没有确认实际协议缺陷时，不修改：

- Topic
- payload
- control command format
- robot MQTT interface behavior

Map V2 的目标不是重写 MQTT 控制协议，而是把地图同步从 MQTT mapJsonUrl 切换为 HTTP。

## Production Direction

正式生产阶段计划：

- MQTT 1883 -> MQTTS 8883
- Robot 使用每设备独立凭证
- Robot 使用设备级 ACL
- APP 不保存长期 MQTT 密钥
- APP MQTT 凭证由 Cloud Server 动态签发
- 限制 EMQX Dashboard 18083 公网访问

## Important

HTTP Auth / Session 和 Map V2 改造与现有 Robot MQTT 控制协议解耦。

Android Map V2 改造不能破坏已经验证的 Robot MQTT 控制/status/remote/cmd 行为。

当前环境详情：

docs/current_environment.md
