# ikuai-geoip-sync 升级指南

> 这份文档由 `/deploy-fnos` 自动生成，由 `/fnos-check-updates` 自动消费。
> 修改前请理解：错误的内容会让自动升级走错路径。

## 升级类型

build

## 上游源码

- git_url: ssh://git@gitea.ilojoli.com:22022/minglei/ikuai-geoip-sync.git
- branch: master
- deployed_commit: 8b6f49af05364baee62e0d1f3d3144a03504a7b9
- upstream_dir: .upstream/

## 镜像信息（仅 image 类型必填）

<!-- build 类型留空 -->
- image:
- tag:

## 部署期修改

机器可应用的 patch 文件：`.upstream/deploy.patch`（0 字节，无修改）

无部署期修改。代码库本身已包含：
- 国内镜像源（`docker.1ms.run/library/python:3.12-slim`，Dockerfile 第 1 行）
- 清华 PyPI 镜像（`PIP_INDEX_URL`，Dockerfile 第 8 行）
- 清华 apt 镜像（Dockerfile 第 12 行）

升级时无需重新应用任何 patch。

## 升级前必须人工确认的事项

- 若新版本引入了新的 Python 依赖，requirements.txt 变更后 docker compose 会自动重新 pip install
- 若新版本修改了 data/ 的数据结构（config.json / auth.json），查看 CHANGELOG 确认是否需要迁移

## 健康探测

- 端点：http://10.0.0.16:8765/api/auth/status
- 期望状态码：200
