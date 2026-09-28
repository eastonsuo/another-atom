# 验证环境登记

本文登记 Another Atom 可以用于开发侧验证的环境类型、不可变版本口径和访问边界。路径登记不构成部署、测试或凭证读取授权。

## 1. 已登记目标

| 标识 | 环境级别 | 可证明范围 | 不可变版本 | 入口与检查 | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| `local-test` | 非生产、本机 | Python 单元/集成测试、静态检查、Studio lint/build；按任务实际装配的本地真实边界 | Git commit；工作区非干净时同时记录 diff 范围 | 仓库根目录执行 `uv run pytest`、`uv run ruff check another_atom tests`；`studio/` 执行 `npm run lint`、`npm run build` | 可用，但不证明 Railway 网络、Volume、私网 executor 或进程重启行为 |

本地测试命令只在合同和改动范围适用时执行，不要求每次机械运行全部检查。使用未提交代码验证时必须记录基线和实际 diff，不能只写 commit。

## 2. Railway 当前登记状态

仓库已经包含：

- `railway.toml`：主服务使用 `Dockerfile`，健康检查为 `/api/health`；
- `railway.executor.toml`：共享执行服务使用 `Dockerfile.executor`，健康检查为 `/health`；
- `docs/design/V1/技术设计/04-[工程]-运行与部署.md`：Railway 主服务、Volume、私网 executor 和验收目标。

仓库当前没有登记能够唯一识别的 Railway 非生产 Project、Environment、服务实例、测试域名或实际版本读回入口。现有设计中的 `production` 配置和示例域名不能推定为非生产环境，也不能供 `validate-in-non-production` 使用。

因此当前状态为：

```text
Railway 非生产部署目标：未登记
Railway 环境验证：BLOCKED
阻塞原因：缺少可唯一识别的非生产环境和不可变版本读回配置
```

这不影响代码实施和本地验证完成，但任何需要证明 Railway 网络、持久化 Volume、主服务与 executor 私网调用、部署后重启恢复或公网页面行为的合同仍属于未完成环境验证。

## 3. 登记 Railway 非生产环境所需字段

开始实际部署或验证前，必须在本文或项目登记的机器专属配置中补齐：

- 环境级别、Railway Project 和 Environment 的唯一标识；
- 主服务与 runtime executor 的唯一服务标识；
- 主服务测试 URL，以及 executor 仅限私网访问的实际入口；
- Git commit、Deployment ID、镜像 Digest 或等价不可变版本标识；
- 主服务与 executor 的实际版本读回方法；
- Volume、数据库和服务依赖的只读就绪检查；
- 验证身份或凭证的安全来源、允许范围和清理责任，不记录明文；
- 允许执行的部署、重启、测试和数据写入动作；
- 失败停止、保留现场和回滚边界。

机器专属路径、账号、Token、Cookie 和 Secret 不写入本文件。目标未登记、身份不匹配或可能指向生产时，只允许只读调查并保持验证阻塞。
