# Kubernetes 部署说明

将 Task Manager API 部署到本地 Minikube 集群的完整指南。

## 目录结构

```
k8s/
├── namespace.yaml     # 命名空间
├── configmap.yaml     # 非敏感配置
├── deployment.yaml    # 部署清单（2 副本 + 资源限制 + 健康探针）
├── service.yaml       # ClusterIP 服务
├── ingress.yaml       # Ingress 入口规则
└── README.md          # 本文档
```

## 前提条件

- [Docker](https://docs.docker.com/get-docker/)（用于构建镜像）
- [Minikube](https://minikube.sigs.k8s.io/docs/start/) v1.30+
- [kubectl](https://kubernetes.io/docs/tasks/tools/) v1.28+

验证安装：

```bash
docker --version
minikube version
kubectl version --client
```

## 1. 启动 Minikube 集群

```bash
minikube start --cpus=2 --memory=4096 --driver=docker
```

验证集群就绪：

```bash
kubectl get nodes
# NAME       STATUS   ROLES           AGE   VERSION
# minikube   Ready    control-plane   1m    v1.35.x
```

## 2. 启用 Ingress 插件

```bash
minikube addons enable ingress
```

验证 ingress-nginx 控制器运行：

```bash
kubectl get pods -n ingress-nginx
```

## 3. 构建 Docker 镜像

有两种方式让 Minikube 使用本地镜像。

### 方式 A：使用 Minikube Docker 守护进程（推荐）

将 shell 指向 Minikube 内部的 Docker 守护进程，直接在其中构建镜像：

```bash
# Linux / macOS
eval $(minikube docker-env)

# Windows (PowerShell)
minikube docker-env | Invoke-Expression

# 构建镜像
docker build -t task-manager-api:slim .

# 构建完成后取消绑定（可选）
# Linux / macOS:  eval $(minikube docker-env -u)
# Windows:        minikube docker-env -u | Invoke-Expression
```

### 方式 B：构建后加载到 Minikube

```bash
# 在宿主机构建
docker build -t task-manager-api:slim .

# 加载到 Minikube
minikube image load task-manager-api:slim
```

验证镜像已加载：

```bash
minikube image ls | grep task-manager
```

> **注意**：Deployment 中已设置 `imagePullPolicy: Never`，确保 Kubernetes
> 使用本地镜像而不尝试从远程仓库拉取。

## 4. 部署 Kubernetes 资源

```bash
# 在项目根目录执行
kubectl apply -f k8s/
```

或逐个应用：

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

## 5. 验证部署

### 检查所有资源

```bash
kubectl get all -n task-manager
```

预期输出：

```
NAME                                   READY   STATUS    RESTARTS   AGE
pod/task-manager-api-xxxx-aaaa         1/1     Running   0          1m
pod/task-manager-api-xxxx-bbbb         1/1     Running   0          1m

NAME                       TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
service/task-manager-api   ClusterIP   10.96.xxx.xxx   <none>        8080/TCP   1m

NAME                               READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/task-manager-api   2/2     2            2           1m
```

### 检查 Pod 状态

```bash
kubectl get pods -n task-manager -o wide
```

### 等待所有 Pod 就绪

```bash
kubectl rollout status deployment/task-manager-api -n task-manager
# deployment "task-manager-api" successfully rolled out
```

### 查看日志

```bash
kubectl logs -n task-manager -l app.kubernetes.io/name=task-manager-api -f
```

## 6. 配置 Ingress 访问

### 方式 A：通过 task-manager.local 域名访问

获取 Minikube IP：

```bash
minikube ip
# 例如: 192.168.49.2
```

将域名解析添加到 hosts 文件：

```bash
# Linux / macOS
echo "$(minikube ip) task-manager.local" | sudo tee -a /etc/hosts

# Windows (PowerShell 管理员)
Add-Content C:\Windows\System32\drivers\etc\hosts "$(minikube ip) task-manager.local"
```

访问 API：

```bash
curl http://task-manager.local/health
# {"status":"healthy"}

curl http://task-manager.local/tasks
# []
```

### 方式 B：通过端口转发访问

无需配置域名，直接转发端口：

```bash
kubectl port-forward -n task-manager svc/task-manager-api 8080:8080
```

在另一个终端：

```bash
curl http://localhost:8080/health
curl http://localhost:8080/tasks
```

### 方式 C：通过 Minikube Service 访问

```bash
minikube service task-manager-api -n task-manager --url
```

## 7. 资源清单说明

### Namespace（namespace.yaml）

创建独立的 `task-manager` 命名空间，隔离应用资源。

### ConfigMap（configmap.yaml）

存储非敏感配置，通过 `envFrom` 注入容器：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `APP_HOST` | `0.0.0.0` | 监听地址 |
| `APP_PORT` | `8080` | 监听端口 |
| `APP_DEBUG` | `false` | 调试模式 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `APP_RATE_LIMIT_ENABLED` | `true` | 启用限流 |
| `APP_RATE_LIMIT_REQUESTS` | `100` | 限流请求数 |
| `APP_RATE_LIMIT_WINDOW_SECONDS` | `60` | 限流时间窗口（秒） |

### Deployment（deployment.yaml）

- **副本数**：2（高可用）
- **镜像**：`task-manager-api:slim`，`imagePullPolicy: Never`
- **资源限制**：
  - CPU: 请求 100m / 限制 200m
  - Memory: 请求 128Mi / 限制 256Mi
- **就绪探针**：HTTP GET `/health`，延迟 3s，间隔 5s
- **存活探针**：HTTP GET `/health`，延迟 10s，间隔 30s
- **滚动更新**：maxUnavailable=0，maxSurge=1

### Service（service.yaml）

- **类型**：ClusterIP（集群内部访问）
- **端口**：8080 → 8080 (http)

### Ingress（ingress.yaml）

- **域名**：`task-manager.local`
- **路径**：`/`（Prefix 前缀匹配，直接透传原始 PATH，不做重写）
- **后端**：`task-manager-api:8080`
- **IngressClass**：`nginx`（通过 `spec.ingressClassName` 指定，未使用已弃用的 `kubernetes.io/ingress.class` 注解）
- **Nginx 注解**：proxy 超时（30s）、SSL 关闭、健康检查路径 `/health`、限流（100 rps / burst 200）

## 8. 常用运维命令

```bash
# 查看资源状态
kubectl get all -n task-manager

# 查看 Pod 详情
kubectl describe pod -n task-manager -l app.kubernetes.io/name=task-manager-api

# 查看日志（实时）
kubectl logs -n task-manager -l app.kubernetes.io/name=task-manager-api -f

# 进入 Pod
kubectl exec -it -n task-manager deploy/task-manager-api -- sh

# 扩缩容
kubectl scale deployment task-manager-api -n task-manager --replicas=3

# 滚动重启
kubectl rollout restart deployment task-manager-api -n task-manager

# 查看滚动更新状态
kubectl rollout status deployment task-manager-api -n task-manager

# 查看部署历史
kubectl rollout history deployment task-manager-api -n task-manager
```

## 9. 更新部署

修改代码后重新部署：

```bash
# 1. 重新构建镜像（使用 Minikube Docker）
eval $(minikube docker-env)          # Linux/macOS
# minikube docker-env | Invoke-Expression  # Windows
docker build -t task-manager-api:slim .

# 2. 触发滚动更新
kubectl rollout restart deployment task-manager-api -n task-manager

# 3. 验证更新
kubectl rollout status deployment task-manager-api -n task-manager
```

## 10. 清理

删除所有资源：

```bash
kubectl delete -f k8s/
```

仅删除命名空间（会级联删除其中所有资源）：

```bash
kubectl delete namespace task-manager
```

停止 Minikube 集群：

```bash
minikube stop
```

删除 Minikube 集群：

```bash
minikube delete
```

## 11. 配置校验

部署前可用 `kubectl --dry-run` 对清单做语法与字段校验，无需真正创建资源。

### 客户端校验（不连接集群）

```bash
kubectl apply --dry-run=client -f k8s/
```

预期输出（每个资源一行 `created (dry run)`）：

```
namespace/task-manager created (dry run)
configmap/task-manager-api-config created (dry run)
deployment.apps/task-manager-api created (dry run)
service/task-manager-api created (dry run)
ingress.networking.k8s.io/task-manager-api created (dry run)
```

### 服务端校验（连接 API Server，验证引用与准入）

```bash
kubectl apply --dry-run=server -f k8s/
```

### 已验证的一致性项

以下交叉引用均已校验通过，修改清单时请保持一致：

| 校验项 | 关联资源 | 期望值 |
|--------|----------|--------|
| Label 选择器 | Deployment.selector ↔ Pod template label | `app.kubernetes.io/name=task-manager-api` |
| Service → Pod | Service.selector ↔ Deployment label | `app.kubernetes.io/name=task-manager-api` |
| Ingress → Service | Ingress.backend.service.name ↔ Service.name | `task-manager-api` |
| Ingress → Service Port | Ingress.backend.port.number ↔ Service.port | `8080` |
| ConfigMap 注入 | Deployment.envFrom.configMapRef.name ↔ ConfigMap.name | `task-manager-api-config` |
| 端口命名 | Deployment.ports.name ↔ Probe.port ↔ Service.targetPort | `http` |
| 资源限制 | Deployment.resources | CPU 100m–200m / Memory 128Mi–256Mi |
| 探针路径 | readinessProbe / livenessProbe | HTTP GET `/health` |

## 12. 故障排查

### Pod 处于 ImagePullBackOff / ErrImagePull

```
原因: Kubernetes 无法找到本地镜像
解决:
  1. 确认使用 Minikube Docker 构建镜像:
     eval $(minikube docker-env)
     docker build -t task-manager-api:slim .
  2. 或加载已构建的镜像:
     minikube image load task-manager-api:slim
  3. 确认 Deployment 中 imagePullPolicy: Never
```

### Pod 处于 CrashLoopBackOff

```bash
# 查看日志
kubectl logs -n task-manager <pod-name>

# 查看事件
kubectl describe pod -n task-manager <pod-name>
```

### 健康探针失败

```bash
# 确认容器内服务正常
kubectl exec -n task-manager <pod-name> -- wget -qO- http://localhost:8080/health
```

### Ingress 无法访问

```bash
# 1. 确认 ingress-nginx 控制器运行
kubectl get pods -n ingress-nginx

# 2. 确认 Ingress 资源已创建
kubectl get ingress -n task-manager

# 3. 确认 hosts 文件配置
# task-manager.local 应指向 minikube ip

# 4. 查看 ingress 控制器日志
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx -f
```

### 无法连接 API Server

```bash
# 检查 Minikube 状态
minikube status

# 如需重启
minikube stop
minikube start
```
