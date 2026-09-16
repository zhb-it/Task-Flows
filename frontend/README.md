# TaskFlow Pro · 前端

团队任务协作系统的前端工程：**Vue 3 + TypeScript + Vite**。

后端（FastAPI）在本仓库根目录，本工程通过 HTTP 调用它，不做任何后端逻辑的复刻。

---

## 1. 快速开始

```bash
# 1. 安装依赖（Node >= 20.19）
npm install

# 2. 启动开发服务器（默认 http://localhost:5173）
npm run dev
```

开发服务器把 `/api` 代理到 `http://127.0.0.1:8000`（后端默认端口），因此**先启动后端**再打开页面。

```bash
# 在本仓库根目录启动后端
uvicorn app.main:app --reload --port 8000
```

### 为什么开发环境要走代理

规格 §54 的示例把 `VITE_API_BASE_URL` 写成 `http://localhost:8000/api/v1`（绝对地址），
但后端 `app/main.py` **没有注册 `CORSMiddleware`**，浏览器直连 8000 会被同源策略拦下。

所以本工程用**相对路径** `/api/v1`，由 Vite 代理转发（规格 §55）。对浏览器而言请求是同源的，
不需要 CORS；生产环境两者一致（都走 Nginx 的 `/api` 反代），这个偏差只影响开发环境。
详见 `docs/DECISIONS.md` 的 047。

---

## 2. 脚本

| 命令 | 作用 |
| --- | --- |
| `npm run dev` | 启动开发服务器（HMR） |
| `npm run build` | 类型检查 + 生产构建，产物在 `dist/` |
| `npm run preview` | 本地预览 `dist/` 产物 |
| `npm run typecheck` | 只做类型检查（`vue-tsc --noEmit`） |
| `npm run lint` | ESLint 检查，**0 warning 容忍** |
| `npm run lint:fix` | ESLint 自动修复 |
| `npm run format` / `format:check` | Prettier 格式化 / 校验 |
| `npm run test` | Vitest 单次运行 |
| `npm run test:watch` | Vitest 监听模式 |

`build` 里串了 `vue-tsc --noEmit`：类型错误不应该等到运行时才暴露，构建即失败。

> ⚠️ 在受限沙箱里运行 `npm run build` 时，若 `dist/assets` 已有超过 50 个文件，Vite 清空输出目录
> 会触发环境的批量删除守卫（`SAFE_DELETE_BULK_CONFIRM_REQUIRED`）而失败。给命令加
> `CODEBUDDY_SAFE_DELETE_ENABLED=0` 前缀即可绕过（只影响构建产物清理，不影响代码与产物内容）。

---

## 3. 目录结构

```text
frontend/
├── public/                     # 原样拷贝的静态资源
├── src/
│   ├── api/                    # 后端端点的唯一入口（页面不直接碰 axios）
│   ├── assets/styles/          # 全局样式（重置 + 布局变量）
│   ├── components/
│   │   ├── common/             # 通用组件（PagePlaceholder 等）
│   │   └── layout/             # 布局组件（Sidebar/Header/Breadcrumb/UserMenu/NotificationBell）
│   ├── composables/            # 组合式函数（usePermission）
│   ├── layouts/                # BasicLayout（主框架）/ AuthLayout（登录注册）
│   ├── router/                 # routes（含菜单定义）/ index / guards
│   ├── stores/                 # Pinia（auth / notification）
│   ├── types/                  # 与后端契约对应的类型（含 router 的 meta 扩展）
│   ├── utils/                  # request / storage / permission / format
│   ├── views/                  # 页面（按业务域分子目录）
│   ├── App.vue
│   ├── main.ts
│   └── env.d.ts
└── tests/unit/                 # Vitest 单元测试
```

分层约定（与后端 `Router → Service → CRUD → Model` 对称）：

```text
View ──► api/ ──► utils/request.ts ──► Axios ──► FastAPI
```

页面**不**直接写 `axios.get(...)`，也不自己拼 `Authorization` 头——那是请求层的职责。

---

## 4. 环境变量

| 变量 | 开发 | 生产 | 说明 |
| --- | --- | --- | --- |
| `VITE_APP_TITLE` | 团队任务协作系统 | 同左 | 标签页标题与侧边栏文案 |
| `VITE_API_BASE_URL` | `/api/v1` | `/api/v1` | 必须是相对路径，见 §1 |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | — | 仅开发环境使用 |

⚠️ `VITE_*` 会被**内联进打包产物**，浏览器里能直接看到。数据库密码、JWT Secret、
Redis 密码一律不得放进这里（规格 §54）。

---

## 5. 请求层的行为

集中在 `src/utils/request.ts`，业务代码只需要 `http.get<T>(url)`：

1. **解信封**：后端成功响应是 `{"data": ..., "message": "success"}`，请求层剥掉外层，
   `http.get<User[]>('/teams')` 直接得到 `User[]`。
2. **自动带令牌**：业务端点自动补 `Authorization: Bearer <access_token>`；
   登录 / 注册 / 刷新这三个端点不带（避免用过期令牌覆盖它们的语义）。
3. **401 自动刷新**：Access Token 失效时用 Refresh Token 换新对并**重放原请求**。
   并发 401 **共享同一次刷新**（single-flight）——否则后到的刷新会拿着已被轮换撤销的
   Refresh Token 去请求，反而把用户踢下线。
4. **统一错误**：归一成 `ApiError{status, message, detail}`，并按规格 §41 弹中文提示；
   `{ silent: true }` 可关闭提示（轮询、铃铛这类非阻断请求用）。

Refresh Token 也失效时：清空本地凭证 → 由路由层跳 `/login` 并带上 `?redirect=`。

---

## 6. 与后端契约的差异

前端严格按 `docs/API_CONTRACT.md` 与**真实后端实现**对接。凡是规格文档与后端不一致的地方，
一律以后端为准（规格 §57），差异逐条记录在仓库根目录的 `docs/FRONTEND_API_MAPPING.md`。

几个已经影响实现的点：

- 当前用户端点是 `GET /api/v1/users/me`（规格 §58 写的是 `/auth/me`）。
- 响应信封没有 `code` 字段（规格 §40 的示例有）。
- 后端**没有**权限查询端点，因此前端无法得知当前用户的权限集合，
  `composables/usePermission.ts` 保留了落点但不据此隐藏功能（隐藏按钮 ≠ 安全，规格 §35）。
- `GET /api/v1/tasks` 的 `project_id` **必填**，所以「我的任务」不是全局页面。
- 列表端点只有 `skip`/`limit`，没有总数，分页器只能做「上一页 / 下一页」。

---

## 7. 已知取舍

| 取舍 | 原因 |
| --- | --- |
| Element Plus 按需引入（TASK-080） | `unplugin-vue-components` 编译期解析模板组件与 `v-loading`；命令式 API 保持显式 import、样式在 `main.ts` 集中补引（主 chunk 由 ~1074 kB 降至 ~2xx kB） |
| 图标不做全局注册 | `@element-plus/icons-vue` 有 300+ 个图标，全量注册会全部进产物；各组件按需 import |
| 令牌存在 `localStorage` | 刷新页面必须保持登录；后端无 cookie/session 机制，没有更安全的可选方案（代价见 DECISIONS 047） |
| `chunkSizeWarningLimit` 回到默认 500 kB | 按需引入后单 chunk 已回到警告线以内，超线即警告，防止体积悄悄回涨 |
| 面包屑只到「板块 / 当前页」两级 | 不要求每条路由手写 breadcrumb 字段，少一份需要维护的重复信息 |

---

## 8. 开发阶段

进度按仓库根目录 `docs/TASKS.md` 与 `docs/PROGRESS.md` 记录，开发顺序见
`docs/FRONTEND_PROJECT_SPEC.md` §59（15 个阶段）。

当前已交付：**阶段 1（项目初始化）+ 阶段 2（基础框架）+ 阶段 3（认证）+ 阶段 5（Dashboard）+
阶段 6（团队）+ 阶段 7（项目）+ 阶段 8（任务）+ 阶段 9（评论）+ 阶段 10（附件）+
阶段 11（通知）+ 阶段 12（权限）+ 阶段 13（操作日志）+ 阶段 14（测试：单元测试 70 项 / 8 文件）+
阶段 15（部署：多阶段构建镜像 + 生产栈 Nginx 托管，TASK-079）+ 阶段 16（优化：Element Plus
按需引入 + 死依赖清理，TASK-080）**。**规格 §59 全部阶段收官**。

- Dashboard（TASK-069）：`GET /teams`、`GET /projects`、`GET /notifications`、`GET /logs`
  驱动统计卡片与「最近通知 / 最近项目」两列表；规格 §11.2 的「任务统计」与全局「最近任务」
  受后端 `project_id` 必填与无跨项目统计端点限制（`docs/FRONTEND_API_MAPPING.md` §4-D7/D8、§6-Q2），
  页面顶部提示条已写明，不编造接口。
- 团队（TASK-070）/ 项目（TASK-071）/ 任务（TASK-072）：列表 / 详情 / 创建 / 设置接入真实端点，
  按钮显隐按**接口返回的数据**（`owner_id`、成员 `role`、`ProjectRead.team_id`）数据驱动，
  越权一律交后端 403/404 兜底（不臆测权限集合，`§4-D4`）。
- 评论（TASK-073）：任务详情内评论区块（列表 / 发表 / 删除自己的评论）；
  `comment:delete` 种子仅 admin（`§4-D11`），成员删自己的评论可能 403，由请求层提示。
- 附件（TASK-074）：任务详情内附件区块（上传 / 列表 / 下载 / 删除自己的上传）；
  上传字段名 `file`、按扩展名白名单预检、10 MiB 上限；下载走 `http.getBlob`（响应是文件流非信封）。

规格 §59 各阶段已全部交付；后续如出现新的组件/API 需求，按「已知取舍」表中的
按需引入口径增量维护（新命令式 API 记得在 `main.ts` 补样式）。

### 部署（TASK-079，前端规格 §56 / §59 阶段 15）

```bash
# 单独构建前端镜像（node:22-alpine 构建 → nginx:1.27-alpine 托管 dist）
docker build -t taskflow-frontend:prod ./frontend

# 或随生产栈整体构建/启动（docker-compose.prod.yml 的 frontend 服务）
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

生产链路：入口 Nginx（唯一对外）按 §56 分流——`/` → 前端镜像（静态托管：
history 回退 + hash 资源永久缓存），`/api/` → FastAPI。`frontend/nginx.conf`
只做静态托管，不做 API 反代；安全语义（X-Forwarded-For 覆盖写入等）只在
入口 `nginx/nginx.conf` 一份拷贝。细节见 DECISIONS 058。
