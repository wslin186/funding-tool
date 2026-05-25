# funding-tool Web UI Design Spec

**Date**: 2026-05-25
**Status**: Brainstorming complete, ready for implementation plan
**Reviewers**: Codex (3 rounds — Section 1+2, Section 3, Section 4)

---

## 0. Goal & Scope

为 funding-tool 项目新增一个 Web UI，作为现有 CLI 的可视化补充。功能覆盖 Feature A（Backtest，公开数据回测）+ Feature B（Account History，需 Binance API key 的资金费历史），让用户在浏览器里跑参数、看图表、管账户。

**部署目标**：与已有的 FutuBinance 系统（同服务器，端口 8000，路径 `/monitor/`）共存于 47.238.248.16，funding-tool 占用端口 8001、路径 `/funding/`。

**UI 约束**：界面**全中文**，任何后端字段名/英文 code 不得直接渲染到 UI，必须经 `labels.ts` 翻译层。

**质量约束**：UI 要好看（抄 FutuBinance 浅色 editorial 主题）、数据呈现要完整（不只摘要、要图表+明细+导出）、上线必须经过 P0/P1 评审。

---

## 1. 项目结构

### 1.1 仓库

funding-tool 仓库**独立**，不与 FutuBinance 共仓。当前 `src/funding_tool/` 已有 CLI + core，本设计在此基础上加 `web/` 子包 + `frontend/` 子项目。

### 1.2 目录布局

```
src/funding_tool/
├── cli/                    # 既有，CLI 入口
├── core/                   # 既有，纯 async service 层
└── web/                    # 新增
    ├── main.py             # FastAPI app + lifespan + CSRF + auth 中间件
    ├── auth.py             # Basic Auth + 失败锁定 + IP 提取
    ├── csrf.py             # CSRF token 生成/校验 + Origin 校验
    ├── secret_store.py     # AES-GCM + SQLite（独立于 CLI keyring）
    ├── audit.py            # 审计日志 JSONL writer
    ├── tasks.py            # 后台任务管理（history 长查询）
    ├── routes/
    │   ├── backtest.py     # POST /api/backtest（同步）
    │   ├── history.py      # POST /api/history → task_id; GET /api/history/result/{id}
    │   ├── accounts.py     # CRUD /api/accounts
    │   ├── csrf.py         # GET /api/csrf（拿 token）
    │   └── meta.py         # GET /api/symbols, GET /api/health
    └── models.py           # Pydantic 包装 core models

frontend/                   # 仓库根，独立子项目
├── package.json            # React 18 + TS + Vite + Recharts（抄 FutuBinance）
├── vite.config.ts          # base: '/funding/', hash chunks
├── tsconfig.json
└── src/
    ├── App.tsx             # 顶部 Tab：回测 / 历史 / 账户
    ├── api.ts              # fetch + Basic auth + CSRF header 注入
    ├── index.css           # 抄 FutuBinance design tokens
    ├── types.ts            # 后端字段类型（英文，不直接渲染）
    ├── labels.ts           # 中文翻译层（field/action/error_code）
    ├── formatters.ts       # 数字/日期格式化（中文千分位、百分号位数）
    ├── csrfStore.ts        # CSRF token memory store + 自动刷新
    └── components/
        ├── BacktestPage.tsx
        ├── HistoryPage.tsx
        ├── AccountsPage.tsx
        ├── SymbolPicker.tsx
        ├── PayoutTimelineChart.tsx
        ├── RateHistogram.tsx
        ├── MonthlyTrendChart.tsx
        ├── SymbolBarChart.tsx
        └── ErrorBanner.tsx

docs/
└── superpowers/specs/2026-05-25-web-ui-design.md  # 本文件

ops/
└── deploy_web.sh           # 部署脚本（同步代码、建用户、装依赖、生成 master.key、reload nginx、restart 服务）
```

### 1.3 进程模型

- **后端**：`funding-tool-web.service`（systemd）→ uvicorn `funding_tool.web.main:app`，绑 `127.0.0.1:8001`，单 worker。
- **前端**：Vite build 产物作为静态文件，由 nginx 直接 serve（不进 Python 进程）。
- **反代**：nginx `location /funding/api/` 转发到 `127.0.0.1:8001/api/`；`location /funding/` serve 静态 + SPA fallback。

### 1.4 与 FutuBinance 共存

| 资源 | FutuBinance | funding-tool |
|---|---|---|
| 端口 | 127.0.0.1:8000 | 127.0.0.1:8001 |
| nginx path | `/monitor/` | `/funding/` |
| systemd unit | `futubinance.service` | `funding-tool-web.service` |
| 系统用户 | `futubinance` | `funding`（新建） |
| 数据目录 | `/opt/futubinance/runtime` | `/var/lib/funding-tool` |
| 日志目录 | `/opt/futubinance/runtime/logs` | `/var/log/funding-tool` |

nginx `location` 必须按精确路径优先：`/funding/api/` > `/funding/` > `/monitor/` > `/`，避免吞配。

---

## 2. API 表面

### 2.1 通用约定

- 路径前缀 `/api/`，全部走 HTTPS（HTTP 308 重定向到 HTTPS）
- 金额字段在 JSON 中用**字符串**（避免 JS Number 精度丢失），后端 Pydantic `Decimal → str` 序列化
- 时间统一 ISO-8601 UTC 带 `Z`
- 写操作（POST/PUT/DELETE）必须带 `X-Funding-Token` header（CSRF），并要 Origin/Referer 匹配 `FUNDING_PUBLIC_ORIGIN`
- 错误统一：`{error: {code, message, field?, error_id?}}`

### 2.2 端点清单

| Method | Path | 用途 | 鉴权 | CSRF |
|---|---|---|---|---|
| GET | `/api/health` | nginx 探活、运维监控 | 匿名 | × |
| GET | `/api/csrf` | 拿 CSRF token（登录后调用） | Basic | × |
| GET | `/api/symbols?q=BTC` | symbol 搜索（缓存 1h） | Basic | × |
| POST | `/api/backtest` | Feature A（同步） | Basic | √ |
| POST | `/api/history` | Feature B（提交后台任务） | Basic | √ |
| GET | `/api/history/result/{task_id}` | 轮询 history 结果 | Basic | × |
| GET | `/api/accounts` | 列账户（不含密钥） | Basic | × |
| POST | `/api/accounts` | 加账户（同步 verify_credentials） | Basic | √ |
| DELETE | `/api/accounts/{name}` | 删账户 | Basic | √ |

### 2.3 请求/响应 schema

**BacktestRequest**
```json
{
  "symbol": "BTCUSDT",
  "side": "LONG | SHORT",
  "start": "2025-01-01T00:00:00Z",
  "end": "2025-12-31T00:00:00Z",
  "size_mode": "BASE | QUOTE | RATE_ONLY",
  "size": "1.5"
}
```

**BacktestResponse**
```json
{
  "input": { ... },
  "event_count": 1095,
  "total_quote": "1234.56",
  "total_base": "0.012",
  "cumulative_rate_pct": "5.43",
  "avg_rate_pct": "0.0149",
  "annualized_pct": "12.34",
  "payments": [
    {
      "timestamp": "...Z",
      "rate": "0.0001",
      "mark_price": "65000.0",
      "quantity_base": "1.5",
      "notional_quote": "97500.0",
      "payment_quote": "9.75"
    }
  ]
}
```

**HistorySubmitResponse**（POST /api/history 返回）
```json
{ "task_id": "uuid", "status": "pending" }
```

**HistoryResultResponse**（GET /api/history/result/{id} 返回）
```json
{
  "status": "pending | running | done | failed",
  "progress": { "current": 3, "total": 7 },
  "result": {
    "start": "...Z",
    "end": "...Z",
    "total": "1234.56",
    "by_symbol": { "BTCUSDT": "800.00" },
    "by_month": { "2025-01": "100.00" },
    "records": [{"timestamp": "...Z", "symbol": "BTCUSDT", "amount_usdt": "0.50", "tran_id": "..."}]
  },
  "error": null
}
```

不分页/不流式：一年 BTCUSDT ≈ 1095 events × 150B ≈ 165KB；响应 > 5MB 时后端拒绝并返 `range_too_large`。

### 2.4 错误码

| code | HTTP | 中文文案 |
|---|---|---|
| `web_auth_required` | 401 | 请先登录 |
| `web_auth_locked` | 429 | 登录次数过多，5 分钟后重试 |
| `csrf_mismatch` | 403 | 安全令牌失效，请刷新页面 |
| `validation_error` | 400 | 输入参数有问题（field 仅暴露白名单字段名） |
| `range_too_large` | 400 | 查询时间范围超过上限 |
| `unknown_symbol` | 404 | 币安没有这个合约，请检查拼写 |
| `exchange_auth_error` | 502 | Binance 接口拒绝了请求，请检查账户 |
| `exchange_rate_limit` | 502 | 币安限流，请稍后重试 |
| `network_error` | 502 | 网络异常 |
| `exchange_error` | 502 | 币安接口异常 |
| `server_error` | 500 | 服务器错误（已记录），err_id 返给用户 |

`validation_error.field` 只允许白名单：`symbol / side / start / end / size_mode / size / account_name / api_key`。其它字段错误统一返 `field: "请求参数"`，避免暴露内部 schema。

---

## 3. 页面布局与数据呈现

### 3.1 全局

- 顶部 Tab：**回测 / 历史 / 账户**，无 React Router，单页面 state 切换
- 错误顶栏（抄 FutuBinance ErrorBanner）：固定页面顶部，红底白字，所有非 401 错误显示在这里
- 401 触发浏览器原生 Basic Auth 弹窗 + 跳登录
- Loading 态：按钮 disabled + 旋转图标 + 文字"查询中"
- 空态：表单空时显示居中提示"请输入参数后开始查询"

### 3.2 Tab 1：回测

**左侧 360px 输入面板**：
- 合约 typeahead（实时调 `/api/symbols`）
- 方向单选：做多 / 做空
- 起止时间：日期选择器 + 快选（7 天 / 30 天 / 本年 / 全部）
- 仓位模式：固定基础数量 / 固定 USDT 名义 / 仅看费率
- 仓位大小（仅看费率时禁用）
- "跑回测"按钮

**右侧结果区四块**：

1. **摘要卡（5 个大数字）**
   - 期数 / 累计费率% / 平均费率% / 年化% / 合计 USDT
   - RATE_ONLY 模式时合计显示 "—"
   - 大字 36px，副标签 12px，颜色按正负值用 `--color-ok / --color-err` 弱背景 + 深字

2. **Recharts ComposedChart 时间线**
   - 左 Y 轴：累计 P&L 折线（粗线 2px，颜色 `--color-accent`）
   - 右 Y 轴：单期费率柱（正绿负红弱底色）
   - X 轴：时间
   - hover tooltip 显示全字段（时间/费率/标记价/数量/名义/支付）

3. **费率分布直方图**
   - 步长用 Freedman-Diaconis 自适应（默认 0.005%）
   - 看偏度

4. **明细表**
   - 列：时间/费率/标记价/支付
   - 可排序、可筛选
   - 虚拟滚动（react-window）
   - 右上角"导出 CSV"按钮，文件名 `funding_backtest_{symbol}_{start}_{end}.csv`

### 3.3 Tab 2：历史

**顶部表单**：账户下拉 / 起止时间 / 合约（可空）/ "查询"按钮

**结果四块**：

1. **摘要卡**：合计 / 笔数 / 平均每月
2. **按月折线图**：叠加 6 个月 EMA 平滑线
3. **按合约分布**：横向 Bar（不用 Pie，超过 8 个合约时折叠"其它"）
4. **原始明细表**：虚拟滚动 + CSV 导出

**长查询体感**：
- 时间跨度 > 90 天时表单下方提示"长时段查询要拉 7 天/页，可能 30-60 秒"
- 后端改成异步任务（见 §4.5）后，前端轮询 `/api/history/result/{id}`，进度条 + loading 转圈
- 用户可继续切换 Tab，回到历史时自动恢复状态

### 3.4 Tab 3：账户

**列表区**（卡片排列，每条一行）：
- name（粗体）
- label（小字灰色）
- key 前 6 位脱敏（如 `abc123...`）
- 创建时间
- 权限报告：只读 ✓（绿） / 交易 ×（红） / 提现 ×（红）
- 操作按钮：测试连接 / 删除

**[添加账户] 按钮 → 模态/抽屉表单**：
- 字段：name / label / api_key / api_secret
- 安全提示文案："只授予 Futures 读取权限，不要开交易和提现"
- 保存时同步调 `verify_credentials`（10s 超时）
- 若返回有 trading/withdrawal 权限，红色横幅警告但**不阻止**保存
- 删除按钮二次确认（弹窗"输入 name 确认"）

### 3.5 i18n 翻译层

**三层结构**：

`types.ts`（仅类型定义，英文字段名）：
```ts
export type BacktestResponse = {
  cumulative_rate_pct: string;
  avg_rate_pct: string;
  // ...
};
```

`labels.ts`：
```ts
export const FIELD_LABELS = {
  cumulative_rate_pct: "累计费率",
  avg_rate_pct: "平均费率",
  annualized_pct: "年化收益率",
  // ...
};
export const ACTION_LABELS = {
  run_backtest: "跑回测",
  delete_account: "删除账户",
};
export const ERROR_MESSAGES = {
  unknown_symbol: "币安没有这个合约，请检查拼写",
  validation_error: "输入参数有问题",
  // ...
};
```

`formatters.ts`：
```ts
formatPct(decimalStr, digits=4) → "0.0149%"
formatUsdt(decimalStr) → "1,234.56 USDT"
formatDate(isoString) → "2025-01-15 08:00 UTC"
```

**强制规则**：组件里不允许写中文字符串字面量；不允许写后端字段名（`cumulative_rate_pct` 等）作为渲染文案。Vitest 单元测试覆盖：每个 FIELD_LABELS / ERROR_MESSAGES key 都必须有对应中文值。

### 3.6 配色（抄 FutuBinance design tokens）

```css
--color-bg: #fbfaf7;          /* 主背景，米白 */
--color-bg-soft: #f6f3ec;     /* 卡片底色 */
--color-text: #1a1a1a;
--color-text-soft: #6b6b6b;
--color-ok: #2f6b3a;          /* 正值/成功 */
--color-err: #9f2f2d;         /* 负值/失败 */
--color-warn: #8f5a00;        /* 警告 */
--color-accent: #1f6c9f;      /* 主强调色，折线、链接 */
--color-border: #e6e0d4;
--shadow-card: 0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.03);
--font-sans: -apple-system, "SF Pro Display", "PingFang SC", "Microsoft YaHei", sans-serif;
```

正负值用 ok/err 弱背景（10% 透明度）+ 深字组合，**不用刺眼红绿**。

---

## 4. 安全 / 错误模型 / 限流 / 测试 / 部署

### 4.1 HTTPS-only

- nginx 80 → 308 永久重定向 → 443
- HSTS: `max-age=31536000; includeSubDomains; preload`
- 后端绑 `127.0.0.1:8001`，**不外暴**
- TLS: Let's Encrypt + certbot 自动续期
- TLS cipher 限制：`ssl_protocols TLSv1.2 TLSv1.3; ssl_ciphers ECDHE+AESGCM:ECDHE+CHACHA20:!aNULL:!MD5:!DSS;`

### 4.2 认证 + CSRF

**Basic Auth**：
- 用户/密码来自 env `FUNDING_AUTH_USER` / `FUNDING_AUTH_PASSWORD`（bcrypt 哈希）
- 失败 5 次锁 300s，**按 X-Real-IP 锁**（见 §4.5 真实 IP 提取）
- `/api/health` 匿名

**CSRF**：
- **Canonical Origin**：env `FUNDING_PUBLIC_ORIGIN=https://<domain>`，启动校验必须 `https://` 开头否则 panic
- 所有 POST/PUT/DELETE 必带 `X-Funding-Token` header
- token 来源：登录后调 `GET /api/csrf` 拿，同时 Set-Cookie：
  - `funding_csrf=<nonce>; Path=/funding/; Secure; HttpOnly=false; SameSite=Strict; Max-Age=3600`
- 后端比对：cookie 中 nonce == header 中 token，且 `Origin == FUNDING_PUBLIC_ORIGIN` 且 `Referer` 前缀 `${PUBLIC_ORIGIN}/funding/`
- token 每小时自动刷新；前端拿到任何 `csrf_mismatch` 立刻 re-fetch 后重试 1 次（仅 1 次防循环）

**CORS**：完全关，同源 only。

### 4.3 Master Key 生命周期

**加载**：
- systemd `LoadCredential=master_key:/etc/funding-tool/master.key`
- 同时 `LoadCredential=master_key_prev:/etc/funding-tool/master.key.prev`（可选，轮换期才有）
- 文件 mode `0400 owner=root`
- 启动时校验：权限正确 / canary 记录解密成功 / 失败 panic
- 启动日志输出 fingerprint `sha256(master_key)[:8]`（hex）

**记录格式**：每条加密记录存 `key_version(uint16) || nonce(12B) || ciphertext || tag(16B)`

**轮换流程**（幂等可恢复）：
1. 运维写 `/etc/funding-tool/master.key.new`（新 key），systemctl reload
2. 启动检测：若 `master.key.new` 存在 → active_version+1，原 active 移到 prev，new 移到 active
3. 后台任务按 PK 顺序逐条 re-encrypt secrets.sqlite，per-row 在 `rotation_state` 字段标 `pending → done`
4. 重启可恢复：扫 `rotation_state=pending` 继续
5. 全表 done 后清空 `rotation_state` 字段、删除 prev key 文件

**泄露应急文档化**：吊销 Binance key → 删 secrets.sqlite → 新 master key → 重新添加账户

### 4.4 错误模型

见 §2.4 错误码表。

**额外约束**：
- 5xx 错误：`error_id = uuid4()`，前端显示 "服务器错误（已记录），错误编号: xxx"；详细 stack trace 只进审计日志
- `exchange_auth_error` 前端文案泛化，不暴露具体凭据状态（"过期 / 权限不足 / IP 白名单"等都统一）
- `validation_error.field` 白名单：见 §2.4
- 响应统一形状：`{error: {code, message, field?, error_id?}}`

### 4.5 限流 / 超时 / 资源上限

**真实 IP 提取**：
- nginx 配 `proxy_set_header X-Real-IP $remote_addr;`
- 后端只信任来自 `127.0.0.1` 的连接传来的 X-Real-IP（其它来源取 peer IP）
- 登录失败计数 + 接口限流 key 都用 X-Real-IP

**应用层限流**（slowapi）：

| 接口 | 限制 |
|---|---|
| POST /api/accounts | verify_credentials 10s 超时；3 次/分钟（按 IP） |
| POST /api/backtest | 时间 ≤ 730 天，事件 ≤ 5000；30 次/分钟；同步总 120s |
| POST /api/history | 时间 ≤ 1095 天；10 次/分钟；**异步任务**，单任务超时 300s |
| GET /api/history/result/{id} | 60 次/分钟 |
| 通用 | gzip ≥1KB；响应 >5MB → 拒绝并返 range_too_large |
| httpx | 单请求 10s；总并发 4 |
| uvicorn | 单 worker |

**nginx 层兜底**：
```nginx
limit_req_zone $binary_remote_addr zone=funding_login:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=funding_api:10m rate=120r/m;
location = /funding/api/csrf { limit_req zone=funding_login burst=5 nodelay; ... }
location /funding/api/ { limit_req zone=funding_api burst=30 nodelay; ... }
```

**History 异步任务**（防止单 worker 被独占）：
- `POST /api/history` 立即返 `task_id`，后端 `asyncio.create_task` 跑实际查询
- 结果写 `/var/lib/funding-tool/tasks/{task_id}.json`，TTL 1h
- 前端轮询 `GET /api/history/result/{id}`（间隔 2s）
- 期间 backtest / accounts / health / auth 仍立即响应（单 worker 也不阻塞，因为是 asyncio）

### 4.6 SQLite

**配置**：WAL + busy_timeout=5000ms + synchronous=NORMAL + foreign_keys=ON

**路径**：`/var/lib/funding-tool/secrets.sqlite`，mode `0600 owner=funding`

**与 CLI 隔离**：**不复用** CLI 的 keyring / cache.sqlite。Web 自己一份。

**Schema**：
```sql
CREATE TABLE accounts (
  name TEXT PRIMARY KEY,
  label TEXT,
  created_at TEXT NOT NULL,
  key_version INTEGER NOT NULL,
  nonce BLOB NOT NULL,
  ciphertext BLOB NOT NULL,
  tag BLOB NOT NULL,
  rotation_state TEXT  -- NULL / 'pending' / 'done'
);
CREATE TABLE canary (
  id INTEGER PRIMARY KEY CHECK (id=1),
  key_version INTEGER NOT NULL,
  nonce BLOB NOT NULL,
  ciphertext BLOB NOT NULL,
  tag BLOB NOT NULL
);
```

### 4.7 审计日志

**格式**：JSONL，每条 `{ts, ip, user, action, target, result, error_code?, error_id?}`

**action 枚举**：`login / login_failed / account_add / account_delete / backtest / history_submit / history_fetch / verify_credentials / csrf_mismatch / rate_limit_hit / master_key_rotation`

**绝不记**：`api_key / api_secret / master fingerprint`

**存储**：
- 路径 `/var/log/funding-tool/audit.jsonl`
- mode `0640 owner=funding group=funding`
- 用 `logging.handlers.WatchedFileHandler`，写失败 fallback 到 syslog
- 磁盘 <500MB 时降级到只记 ERROR 级别

**logrotate** (`/etc/logrotate.d/funding-tool`)：
```
/var/log/funding-tool/audit.jsonl {
  daily
  rotate 90
  compress
  missingok
  copytruncate
  size 100M
  notifempty
}
```

### 4.8 测试

**单元（pytest）**：
- `secret_store`：加密/解密、key_version 切换、轮换 state machine
- `auth`：bcrypt 校验、锁定计数、X-Real-IP 提取
- `csrf`：token 生成/校验、Origin/Referer 匹配
- `formatters`：边界（0、负、超大、Decimal 精度）
- `labels`：全部 FIELD_LABELS / ERROR_MESSAGES key 都必须有中文值
- 错误码映射：每个 core 错误 → web 错误 → HTTP status 对得上

**集成（@pytest.mark.integration）**：
- FastAPI test client → login → CSRF → backtest 全链路
- respx mock Binance API
- 长查询：mock 7 天/页迭代 5 次，验证 history task 流转

**前端单元（Vitest）**：
- components 关键交互（点击 / 表单提交 / 错误显示）
- labels 全覆盖（每个英文 key → 非空中文）
- formatters 边界

**安全回归**：
- CSRF：缺 token / 错 token / 错 Origin / 错 Referer → 拒
- Basic Auth：5 次错 → 锁 300s
- master key 错误 → 启动 panic
- 限流：超阈值 → 429

**必跑 CI 检查**：
- `grep -rn "float(" src/funding_tool/web/` 必须返回 0（已有 `tests/unit/test_no_float_in_core.py` 同款规则扩展到 web）
- `npm test` + `tsc --noEmit`
- `ruff check` + `mypy src`

### 4.9 部署

#### 4.9.1 nginx 配置（追加到现有 hedge 站点）

```nginx
# /etc/nginx/sites-available/hedge
server {
    listen 80;
    server_name <domain>;
    return 308 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name <domain>;

    ssl_certificate     /etc/letsencrypt/live/<domain>/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/<domain>/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE+AESGCM:ECDHE+CHACHA20:!aNULL:!MD5:!DSS;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # 现有 FutuBinance
    location /monitor/ { proxy_pass http://127.0.0.1:8000/; ... }

    # 新增 funding-tool
    location = /funding/api/csrf {
        limit_req zone=funding_login burst=5 nodelay;
        proxy_pass http://127.0.0.1:8001/api/csrf;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Host $host;
    }
    location /funding/api/ {
        limit_req zone=funding_api burst=30 nodelay;
        proxy_pass http://127.0.0.1:8001/api/;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Host $host;
        proxy_read_timeout 360s;
    }
    location /funding/ {
        alias /opt/funding-tool/frontend/dist/;
        try_files $uri $uri/ /funding/index.html;
        location ~* \.(js|css|woff2|svg)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
        location = /funding/index.html {
            add_header Cache-Control "no-cache, must-revalidate";
        }
    }
}
```

#### 4.9.2 systemd unit

```ini
# /etc/systemd/system/funding-tool-web.service
[Unit]
Description=funding-tool Web (FastAPI + uvicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
User=funding
Group=funding
WorkingDirectory=/opt/funding-tool

LoadCredential=master_key:/etc/funding-tool/master.key
LoadCredential=master_key_prev:/etc/funding-tool/master.key.prev
EnvironmentFile=/etc/funding-tool/web.env
# web.env 内容：FUNDING_AUTH_USER, FUNDING_AUTH_PASSWORD (bcrypt), FUNDING_PUBLIC_ORIGIN

ExecStart=/opt/funding-tool/.venv/bin/uvicorn funding_tool.web.main:app \
    --host 127.0.0.1 --port 8001 --workers 1

Restart=on-failure
RestartSec=5
WatchdogSec=30

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/funding-tool /var/log/funding-tool
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_UNIX
RestrictNamespaces=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM

[Install]
WantedBy=multi-user.target
```

#### 4.9.3 部署脚本 `ops/deploy_web.sh`

主要步骤：
1. rsync 代码到 `/opt/funding-tool/`（exclude `.venv`, `node_modules`, `tests/`）
2. 创建 `funding` 系统用户（`useradd -r -s /usr/sbin/nologin funding`），如果已存在则跳过
3. 创建数据/日志目录：`/var/lib/funding-tool`、`/var/log/funding-tool`，owner=funding，mode 0750
4. `uv sync --frozen` 创建/更新 .venv
5. `cd frontend && npm ci && npm run build`，产物在 `frontend/dist/`
6. 首次部署生成 master.key：`openssl rand 32 > /etc/funding-tool/master.key; chmod 400; chown root:root`
7. `cp ops/funding-tool-web.service /etc/systemd/system/`
8. `cp ops/logrotate.funding-tool /etc/logrotate.d/funding-tool`
9. `systemctl daemon-reload && systemctl restart funding-tool-web`
10. `nginx -t && systemctl reload nginx`
11. 探活：`curl -fsS http://127.0.0.1:8001/api/health`

---

## 5. Out of Scope（不做）

- 多用户：仍是单一 Basic Auth 凭据（用户级别隔离不在本期）
- WebSocket / 实时推送：所有数据按请求-响应模式拉
- 移动端响应式：桌面优先（FutuBinance 也只做桌面）
- React Router：单页 Tab 切换够用
- 国际化切换：仅中文（labels.ts 是翻译层，不是切换层）
- Docker：直接 systemd 部署，与 FutuBinance 一致
- Sentry / 外部 APM：本期只做本地审计日志 + journalctl

---

## 6. 关键决策记录

| 决策点 | 选择 | 理由 |
|---|---|---|
| 前端栈 | React 18 + TS + Vite + Recharts + 自定义 CSS | 抄 FutuBinance；避免引入新依赖（如 Tailwind） |
| 后端栈 | FastAPI + uvicorn 单 worker | 与 core async 接口天然契合；单 worker 简化锁定/CSRF 状态 |
| Key 存储 | AES-GCM + SQLite（独立于 CLI keyring） | 服务端无桌面 keyring；多账户友好；轮换可控 |
| Auth | HTTP Basic + bcrypt + 失败锁定 | 抄 FutuBinance；够用；HTTPS 强制保护 |
| Master key 来源 | systemd LoadCredential | 比 EnvironmentFile 安全（不进 systemctl show 输出） |
| 长查询模式 | history 异步任务 + 轮询 | 防止单 worker 被独占；用户体感更好 |
| UI 语言 | 全中文 + labels.ts 翻译层 | 用户硬约束；types.ts 仅作类型不渲染 |
| 部署方式 | systemd + nginx，与 FutuBinance 同机 | 用户硬约束 |

---

## 7. Codex 评审追溯

| 段 | 文件 | 主要 finding | 是否消化 |
|---|---|---|---|
| 1+2 | `design-sec1-2.md` | P0: HTTPS-only + master key 生命周期；P1: verify 超时、payload 上限、错误绑 status、SQLite WAL、CSRF；P2: nginx location 优先级、审计日志 | √ 全部消化进 §4 |
| 3 | `design-sec3.md` | 长查询体感、错误顶栏、键盘可达、Recharts 主题、图表选型（Pie → Bar） | √ 消化进 §3 |
| 4 | `design-sec4.md` | P1: master key 轮换 keyring、X-Real-IP、CSRF canonical origin、CSRF token 下发；P2: 错误文案泛化、history 异步、审计日志硬化、systemd sandbox | √ 全部消化进 §4 当前版本 |

---

## 8. Open Questions（实现期再决）

- 日期选择器组件：抄 FutuBinance 的还是用 `react-day-picker`？（FutuBinance 自己实现的，可能要抄过来）
- 前端表格虚拟滚动：`react-window` vs `@tanstack/react-virtual`？倾向前者（更轻）
- CSRF token 失效后的重试策略上限：当前定 1 次，要不要可配置？
- 是否需要在审计日志里加 `request_id` 用于 trace 关联？（默认值得加，与 error_id 不同语义）

这些不阻塞实现计划，可以在 writing-plans 阶段细化或推迟到具体任务里决。
