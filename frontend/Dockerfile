# TaskFlow Pro — 前端镜像（TASK-079；前端规格 §56「生产环境架构」/ §59 阶段 15）
#
# 多阶段构建：
#
#     阶段 1 (build)  : node → npm ci → vite build → dist/
#     阶段 2 (运行时) : nginx → 只拷贝 dist/ 与 frontend/nginx.conf
#
# 为什么要多阶段而不是「宿主上构建好 dist 再 COPY」：
#   ① 构建过程（node_modules ≈ 数百 MB、npm 缓存）不进入最终镜像——运行时镜像里
#      只有静态文件与 nginx，体积小、攻击面小；
#   ② 构建在 Docker 内自包含：任何有 Docker 的机器 `docker build` 一次成功，
#      不依赖宿主上的 Node 版本（本仓库开发用 Node 22，镜像钉 node:22-alpine
#      保持一致）；
#   ③ dist 是**产物**而不是源码：生产栈禁止挂宿主目录（test_no_source_code_
#      bind_mounts），把构建搬进镜像正是为了让 dist 随镜像走。
#
# npm ci 使用 package-lock.json 中记录的 resolved 地址（本项目锁定
# registry.npmmirror.com，见 TASK-065 决策），不依赖构建机的 npm 配置。

# ---------------------------------------------------------------------------
# 阶段 1：构建（Node 与本地开发版本一致，见 frontend/README「工具链」）
# ---------------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# 先只拷贝清单文件再 npm ci：依赖不变时，改源码不会打穿这一层缓存。
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# 再拷贝源码并构建（tsc 类型检查 + vite build，见 package.json 的 build 脚本）。
# .dockerignore 已排除 node_modules / dist / tests，拷贝进来的只有构建所需内容。
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
# 阶段 2：运行时（与入口 Nginx 同版本线，见 docker-compose.prod.yml 的 nginx 服务）
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

# SPA 服务器配置（静态托管 + history 回退 + 资源缓存；API 路由不在这层——
# 「/ 静态、/api/ 反代」的分流由入口 Nginx 统一负责，理由见 nginx/nginx.conf）。
COPY nginx.conf /etc/nginx/nginx.conf

# vite build 产物：assets/ 带 content hash（可永久缓存），index.html 是入口。
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# nginx 镜像默认前台运行，无需 CMD 覆盖；健康检查由 compose 定义
#（探自有的 /nginx-health，与入口 Nginx 同一思路：只回答「这层还活着」）。
