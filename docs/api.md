# Cloud Server HTTP API

当前 HTTP API 由 FastAPI 提供，通过 Nginx port 80 对外访问。

## Health

GET /health

成功：

HTTP 200

{"status":"ok"}

## Authentication

POST /api/auth/login

登录成功返回：

- access_token
- refresh_token
- token_type
- expires_in
- refresh_expires_in

当前：

- Access Token: 3600 seconds
- Refresh Token: 2592000 seconds

POST /api/auth/refresh

使用当前 Refresh Token 换取：

- new Access Token
- new Refresh Token

成功刷新后旧 Refresh Token 立即失效。

POST /api/auth/logout

注销当前 Refresh Token Session。

GET /api/users/me

返回当前登录用户：

- id
- email
- display_name
- status

## Devices

GET /api/devices

返回当前用户绑定的设备。

字段：

- device_id
- display_name
- role
- permissions

当前角色：

- admin
- operator
- viewer

## Jobs

GET /api/jobs?device_id=<device_id>

需要当前用户与设备存在绑定关系。

## Wi-Fi

GET /api/devices/<device_id>/wifi

读取设备 Wi-Fi 状态。

PUT /api/devices/<device_id>/wifi

修改设备 Wi-Fi 配置。

当前要求：

- admin

## Firmware

GET /api/firmware/latest?device_id=<device_id>

固件信息按设备隔离。

没有对应固件时：

HTTP 404

POST /api/firmware/upgrade

当前要求：

- admin

当前升级接口仍属于硬件 OTA 联调占位接口。

## Authorization

设备访问权限由：

user_device_bindings

控制。

没有设备绑定：

HTTP 404

角色不允许执行操作：

HTTP 403

## Authentication Errors

无效或过期 Access Token：

HTTP 401

无效 Refresh Token：

HTTP 401

disabled 用户：

HTTP 403

## Notes

当前 API 实际运行状态和认证策略以：

docs/current_environment.md

为准。
