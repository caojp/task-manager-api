# Task Manager API

[![CI](https://github.com/caojp/task-manager-api/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/caojp/task-manager-api/actions/workflows/ci.yml)

DevOps 面试作业：基于 Python 3.11 + FastAPI 开发的任务管理 REST API，包含代码风格检查、单元测试、Docker 容器化、Minikube K8s 部署，以及 GitHub Actions CI/CD 流水线。

## 项目简介

Task Manager API 提供标准 RESTful 风格的任务管理接口，支持任务的创建、查询、更新、删除，并具备以下工程能力：

- 统一的错误响应与请求级日志
- 基于 IP 的速率限制（100 请求 / 60 秒）
- 输入校验（Pydantic）与健康检查端点
- 多阶段 Docker 构建（镜像 ~100MB），非 root 用户运行
- Minikube 本地部署（2 副本 + 健康探针 + Ingress 路由）
- GitHub Actions 流水线（Lint / Test / Build / Trivy 漏洞扫描）

## 技术栈说明

| 类别 | 组件 | 版本 | 说明 |
|------|------|------|------|
| 语言 | Python | 3.11 | 运行时 / 开发基础 |
| Web 框架 | FastAPI | 0.141.1 | ASGI，自动生成 OpenAPI |
| 数据校验 | Pydantic / pydantic-settings | 2.x | 请求校验与环境配置 |
| 限流 | limits | 3.x | Starlette 中间件实现 |
| ASGI 服务器 | Uvicorn | 0.30+ | 生产 HTTP 服务器 |
| 测试 | pytest + httpx | 8.x / 0.27+ | 单元测试 & TestClient |
| 代码检查 | Ruff | 0.6+ | Lint + Format，替代 flake8 + black |
| 类型检查 | mypy | 1.11+ | 可选静态类型检查 |
| 容器 | Docker / Dockerfile 多阶段 | Alpine 3.11-slim 基础 | 最终镜像 ~100MB |
| 安全扫描 | Trivy | - | CI 中扫描镜像漏洞 |
| K8s | Minikube + NGINX Ingress | v1.35.x | 本地集群部署 |
| CI | GitHub Actions | - | Lint → Test → Build → Scan |

## API 概览

| 方法 | 路径 | 功能 | 状态码 |
|------|------|------|--------|
| GET | `/health` | 健康检查 | 200 |
| GET | `/tasks` | 获取全部任务 | 200 |
| GET | `/tasks/{id}` | 获取单个任务 | 200 / 404 |
| POST | `/tasks` | 创建任务 | 201 / 422 |
| PUT | `/tasks/{id}` | 更新任务 | 200 / 404 / 422 |
| DELETE | `/tasks/{id}` | 删除任务 | 204 / 404 |

所有错误响应统一格式：

```json
{
  "detail": "具体错误信息",
  "request_id": "唯一请求ID"
}
```

OpenAPI 文档：启动服务后访问 `http://localhost:8080/docs`。

## 本地开发环境搭建步骤

### 1. 克隆仓库

```bash
git clone https://github.com/caojp/task-manager-api.git
cd task-manager-api
```

### 2. 创建虚拟环境并安装依赖

推荐 Python 3.11：

```bash
# 创建虚拟环境
python -m venv .venv
# 激活
# Linux / macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# 安装开发依赖（包含 lint、测试）
pip install -r requirements-dev.txt
```

### 3. 本地启动服务

```bash
# 开发模式（热重载）
uvicorn app.main:app --reload --port 8080
# 或直接运行
APP_PORT=8080 uvicorn app.main:app --host 0.0.0.0 --port 8080
```

验证：

```bash
curl http://localhost:8080/health
# {"status":"healthy"}
```

### 4. 本地代码检查

```bash
# Lint
ruff check .

# 自动修复
ruff check --fix .

# 格式化
ruff format .

# 格式化检查（不修改）
ruff format --check .

# 单元测试
pytest tests/ -v
```

## Docker 构建和运行说明

### 构建镜像

```bash
docker build -t task-manager-api:slim .
```

### 运行容器

```bash
# 默认端口 8080
docker run --rm -p 8080:8080 task-manager-api:slim

# 通过环境变量修改端口
docker run --rm -p 9000:9000 -e APP_PORT=9000 task-manager-api:slim
```

### 验证

```bash
curl http://localhost:8080/health
curl http://localhost:8080/tasks
# []
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"写 README","description":"更新项目文档","priority":"medium"}'
```

### 使用 docker-compose（可选）

```bash
docker compose up --build
# 访问 http://localhost:8080
```

### 镜像特性

- 多阶段构建：builder 阶段安装依赖，runtime 阶段仅保留运行时文件
- 基础镜像：`python:3.11-alpine`（国内镜像源 `docker.m.daocloud.io`）
- 最终体积：约 100MB（要求 150MB 以内）
- 非 root 用户：`appuser`（UID 非特权）
- `.dockerignore` 排除：`__pycache__`、`.venv`、`.git`、`tests/` 等

## Minikube 部署步骤

完整流程见 [k8s/README.md](k8s/README.md)，以下是精简版。

### 1. 启动集群并启用 Ingress

```bash
minikube start --cpus=2 --memory=4096 --driver=docker
minikube addons enable ingress
```

### 2. 将镜像加载到 Minikube

```bash
# 方式 A：使用 Minikube Docker 守护进程构建（推荐）
eval $(minikube docker-env)          # Linux / macOS
# minikube docker-env | Invoke-Expression   # Windows PowerShell
docker build -t task-manager-api:slim .
eval $(minikube docker-env -u)       # 取消绑定

# 方式 B：在宿主机构建后导入
docker build -t task-manager-api:slim .
minikube image load task-manager-api:slim
```

> Deployment 使用 `imagePullPolicy: Never`，确保 Kubernetes 只用本地镜像。

### 3. 部署全部资源

```bash
kubectl apply -f k8s/
```

资源清单：

- [namespace.yaml](k8s/namespace.yaml)：`task-manager` 命名空间
- [configmap.yaml](k8s/configmap.yaml)：端口 / 日志 / 限流等非敏感配置
- [deployment.yaml](k8s/deployment.yaml)：2 副本 + 资源限制 + Readiness/Liveness 探针
- [service.yaml](k8s/service.yaml)：ClusterIP 服务，暴露 8080
- [ingress.yaml](k8s/ingress.yaml)：`task-manager.local` 域名入口

### 4. 验证部署

```bash
# 等待滚动完成
kubectl rollout status deployment/task-manager-api -n task-manager --timeout=120s

# 查看资源
kubectl get all -n task-manager
```

### 5. 配置域名访问

```bash
# 获取 Minikube IP
minikube ip
# 假设输出 192.168.49.2

# Linux / macOS
echo "$(minikube ip) task-manager.local" | sudo tee -a /etc/hosts

# Windows (PowerShell 管理员)
Add-Content C:\Windows\System32\drivers\etc\hosts "$(minikube ip) task-manager.local"
```

### 6. 通过 Ingress 调用 API

```bash
curl http://task-manager.local/health
# {"status":"healthy"}

curl http://task-manager.local/tasks
# []
```

### 7. 快速端口转发（跳过 Ingress）

```bash
kubectl port-forward -n task-manager svc/task-manager-api 8080:8080
curl http://localhost:8080/health
```

部署手册更多内容（更新、清理、故障排查）：[k8s/README.md](k8s/README.md)。

## CI/CD 流水线

### 触发条件

- Push 到 `main` 分支
- Pull Request 到 `main` 分支

配置文件：[.github/workflows/ci.yml](.github/workflows/ci.yml)

### 阶段与任务

| 阶段 | Job | 任务 | 失败后行为 |
|------|-----|------|-----------|
| 1 | Lint | `ruff check` + `ruff format --check` | 阻止后续 Test/Build/Scan |
| 2 | Test | `pytest tests/ -v` | 阻止后续 Build/Scan |
| 3 | Build | 构建 Docker 镜像并推送到 GHCR，标签：`sha-<commit-sha>`、`latest`、分支名 | 阻止后续 Security Scan |
| 4 | Security Scan | Trivy 扫描镜像漏洞（CRITICAL/HIGH），发现即失败；Sarif 报告上传 GitHub Security | 流水线失败 |

### 镜像标签规范

构建的镜像会推送到 GitHub Container Registry（GHCR）：

```
ghcr.io/caojp/task-manager-api:sha-<short-sha>
ghcr.io/caojp/task-manager-api:latest    # main 分支推送时
ghcr.io/caojp/task-manager-api:<branch>
```

### CI 状态徽章

本文档顶部的 Badge 指向默认分支 `main` 的最近一次流水线运行结果。

> 提示：以上 Badge、克隆地址、GHCR 镜像路径均使用实际 GitHub 用户名 `caojp`，如需 fork 后自用，请将其替换为你自己的用户名。

## 分支与 Commit 规范

- 分支：`main` 稳定分支（禁止直接 push），功能开发使用 `feature/*`
- Commit Message：遵循 [Conventional Commits](https://www.conventionalcommits.org/)
  - `feat: ...` 新功能
  - `fix: ...` 修复 bug
  - `docs: ...` 文档更新
  - `refactor: ...` 重构
  - `test: ...` 测试
  - `ci: ...` 流水线
  - `docker: ...` 容器
  - `k8s: ...` K8s 清单

### 最终提交 Commit Message

```
feat: complete homework submission
```

或：

```
docs: add homework submission
```

## 屏幕截图（示例）

### kubectl get all -n task-manager 输出示例

```
NAME                                      READY   STATUS    RESTARTS   AGE
pod/task-manager-api-76d58dbff8-2wztv    1/1     Running   0          2m
pod/task-manager-api-76d58dbff8-vh5l7    1/1     Running   0          2m

NAME                         TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
service/task-manager-api     ClusterIP   10.96.161.88    <none>        8080/TCP   2m

NAME                                 READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/task-manager-api     2/2     2            2           2m

NAME                                            DESIRED   CURRENT   READY   AGE
replicaset.apps/task-manager-api-76d58dbff8     2         2         2       2m
```

### API 调用成功示例

```bash
$ curl http://task-manager.local/health
{"status":"healthy"}

$ curl -X POST http://task-manager.local/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"完成部署文档","description":"编写 README","priority":"high","status":"in_progress"}'
{"id":1,"title":"完成部署文档","description":"编写 README","priority":"high","status":"in_progress","created_at":"2026-08-10T10:00:00Z","updated_at":"2026-08-10T10:00:00Z"}

$ curl http://task-manager.local/tasks
[{"id":1,"title":"完成部署文档","description":"编写 README","priority":"high","status":"in_progress","created_at":"2026-08-10T10:00:00Z","updated_at":"2026-08-10T10:00:00Z"}]
```

## 许可证

[LICENSE](LICENSE)
