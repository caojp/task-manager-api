# Task Manager API
DevOps面试作业：基于Python3.11开发的任务管理REST API，完整包含容器化、Minikube K8s部署、GitHub Actions CI/CD流水线。

## 分支管理规范
- main：稳定可运行主分支，禁止直接push，仅通过PR合并
- feature/*：功能开发分支，如feature/api-crud、feature/health-check

## Commit 规范（Conventional Commits）
feat: 新增功能
fix: 修复bug
docs: 更新文档
refactor: 代码重构
test: 新增单元测试
ci: 修改流水线配置
docker: 容器相关改动
k8s: k8s资源清单改动