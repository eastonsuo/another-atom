# Document Preview 丢失 ES Module 执行语义

[toc]

> 类型：Bug｜领域：工程｜状态：待办｜严重程度：P1｜日期：2026-07-16｜版本范围：V1

- **关联 Review：** [Engineer 项目源码 Contract 缺口](../../review/待办/22-[工程]-2026-07-14-Engineer项目源码Contract缺口.md)
- **既有 Design：** [通用源码与 Runtime 校验 Contract](../../design/V1/技术设计/12-[工程][TODO]-通用源码与Runtime校验Contract.md)
- **关联 Issue：** [#3](https://github.com/eastonsuo/another-atom/issues/3)

## 现象

项目源码和 Runtime 校验完成后，Studio Preview 能显示 HTML/CSS 外壳，但依赖 ES Module 初始化的主体内容没有出现。用户看到的是空白业务区域，而不是明确的 Preview 执行错误。

## 既有预期与实际行为

- **预期：** Document Preview 消费权威 SourceBundle 时，应保留 `index.html` 已声明的脚本执行语义；`<script type="module" src="...">` 内联后仍必须作为 Module 执行。
- **实际：** `buildDocumentPreview()` 为本地 `script[src]` 新建一个不带属性的 `<script>`，只复制脚本内容。原节点的 `type="module"` 及其他执行属性被丢弃，ES Module 源码按 classic script 执行。

## 代码证据

`studio/src/components/PreviewApp.tsx` 的 `buildDocumentPreview()` 当前执行：

1. 找到所有 `script[src]`；
2. 创建新的 `<script>`；
3. 只设置 `textContent`；
4. 用新节点替换原节点。

该路径没有复制原节点属性，因而确定性丢失 `type="module"`。截图中的空白主体与此缺陷一致；仅凭截图不能判断浏览器控制台中的具体异常文本。

## 根因

Preview 物化本地资源时把“替换资源地址”和“重建脚本节点”合并处理，但没有把脚本属性视为 SourceBundle/Document 语义的一部分。该行为违反既有 Document Preview 应消费并保留权威源码语义的设计，不需要新增产品或技术设计。

## 修复边界

- 内联本地脚本时保留 `type`、`async`、`defer`、`nomodule`、`crossorigin`、`referrerpolicy` 等不与本地 `src` 冲突的原始属性；
- 移除已经被内联的 `src`，不得重新发起本地路径请求；
- 网络防护脚本和 Content Security Policy 继续由 Preview 管理；
- 不借本 Bug 改变 Runtime Contract、项目类型或 SourceBundle 结构。

## 验收条件

1. 含 `<script type="module" src="app.js">` 的 Document Preview 能执行模块入口并渲染初始化内容；
2. classic script 的现有 Preview 行为不回退；
3. Preview 单元测试覆盖脚本属性保留和本地 `src` 移除；
4. Railway 部署后用实际项目验证空白主体恢复，且控制台没有因脚本类型丢失产生的语法错误。

## 2026-07-16 Update：代码修复与本地检查

`studio/src/components/PreviewApp.tsx` 已改为克隆原 `script[src]` 节点，移除已经内联的 `src` 和不再适用的 `integrity`，同时保留 `type="module"` 等原始执行属性。Studio 的 `npm run lint` 与 `npm run build` 已通过。

当前尚缺实际 Document Preview 的浏览器回归和 Railway 部署证据，因此本 Bug 继续保留在`待办`。
