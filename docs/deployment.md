# Cloud Server Deployment

## Deployment Root

/opt/cloud-server

HTTP 服务 Compose：

/opt/cloud-server/deploy/docker-compose.yml

MQTT 服务 Compose：

/opt/cloud-server/mqtt/docker-compose.yml

## HTTP Service

运行 HTTP 服务相关 Docker Compose 命令时：

cd /opt/cloud-server/deploy

当前服务：

- vgsolar-nginx
- vgsolar-api
- vgsolar-postgres

## MQTT Service

当前 MQTT 服务：

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

0002_app_platform_v1

Migration chain：

0001_baseline_existing
    ->
0002_app_platform_v1

完整 migration chain 已经通过全新空数据库验证。

## Environment Variables

HTTP 服务环境变量：

/opt/cloud-server/deploy/.env

包含：

- PostgreSQL
- JWT
- Access Token 生命周期
- Refresh Token 生命周期
- Session policy
- Bootstrap account
- Map configuration

不要将 .env 内容复制到项目文档或日志。

## Current Environment

执行任何部署修改前先阅读：

docs/current_environment.md

## Disaster Recovery

改造前恢复点：

/opt/cloud-server/backups

baseline：

20260817_174934

这些灾难恢复文件不得作为普通临时文件清理。
