# =============================================================================
# Stage 1: 构建环境 —— 安装依赖到独立目录
# =============================================================================
FROM docker.m.daocloud.io/library/python:3.11-alpine AS builder

# 设置工作目录
WORKDIR /build

# 安装构建期依赖（musl + gcc + libffi）
# Alpine 用 musl libc，比 glibc 体积小很多
RUN apk add --no-cache gcc musl-dev libffi-dev

# 先复制依赖声明，利用 Docker 缓存层机制
COPY requirements.txt .

# 将依赖安装到独立 prefix，便于下一阶段仅拷贝必要文件
# 使用清华 PyPI 镜像加速；--no-compile 跳过 .pyc 编译以减小体积
RUN pip install --no-cache-dir --no-compile --prefix=/install \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt \
    && find /install -depth -type d -name "__pycache__" -exec rm -rf {} + \
    && find /install -depth -type d -name "tests" -exec rm -rf {} + \
    && find /install -depth -type f -name "*.pyc" -delete


# =============================================================================
# Stage 2: 运行时镜像 —— 最小化体积
# =============================================================================
FROM docker.m.daocloud.io/library/python:3.11-alpine AS runtime

# 环境变量（可通过 docker run -e 覆盖）
ENV APP_HOST=0.0.0.0 \
    APP_PORT=8080 \
    APP_RATE_LIMIT_ENABLED=true \
    APP_RATE_LIMIT_REQUESTS=100 \
    APP_RATE_LIMIT_WINDOW_SECONDS=60 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# 创建非 root 用户（Alpine 用 addgroup/adduser）
RUN addgroup -S appuser && adduser -S -G appuser -h /app -s /sbin/nologin appuser

WORKDIR /app

# 从构建阶段拷贝已安装的依赖（仅 site-packages 与可执行文件）
COPY --from=builder /install /usr/local

# 拷贝应用源码
COPY --chown=appuser:appuser app ./app

# 切换到非 root 用户
USER appuser

# 暴露端口（默认 8080，可通过 APP_PORT 环境变量覆盖）
EXPOSE 8080

# 健康检查（默认端口 8080，如修改 APP_PORT 需同步调整）
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health').read() or sys.exit(1)"]

# 启动 uvicorn，shell 形式以支持 APP_PORT 环境变量插值
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8080}"
