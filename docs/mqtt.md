# MQTT Environment

## Broker

当前 MQTT Broker：

EMQX

Container：

robot-emqx

Current version:

5.8.6

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

## Protocol Stability

当前 Robot 与 APP MQTT 通信已经完成联调。

当前阶段 MQTT 协议视为稳定边界。

没有确认实际协议缺陷时，不修改：

- Topic
- payload
- control command format
- robot MQTT interface behavior

## Production Direction

正式生产阶段计划：

- MQTT 1883 -> MQTTS 8883
- Robot 使用每设备独立凭证
- Robot 使用设备级 ACL
- APP 不保存长期 MQTT 密钥
- APP MQTT 凭证由 Cloud Server 动态签发
- 限制 EMQX Dashboard 18083 公网访问

## Important

HTTP Auth / Session 改造与现有 Robot MQTT 协议解耦。

Android Auth 改造不能破坏已经验证的 Robot MQTT 控制协议。

当前环境详情：

docs/current_environment.md
