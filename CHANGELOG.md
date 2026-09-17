# Changelog

## 2.2.0 — 2026-09-17

### 原版 GUI 桥模式（默认）

- skill 目录外的 `novelborne-3.0.1` 应用以 `FATE_SKILL_BRIDGE=1` 启动：前端零改动，`fe.make_client` 在桥模式下返回 `SkillBridgeClient`，所有模型请求落盘为 `<APP>/var/bridge/jobs/<id>.request.json`，由助手 CLI 应答；全程无 API key、无“AI 配置”，凭据门禁在桥模式下全部放行。
- `scripts/runtime.py` 新增三个桥命令：`bridge-pending [--wait S]`、`bridge-show --job ID`、`bridge-respond --job ID (--file F | --text T | --error E)`。var 目录经 run_app.py 标记自动发现；中文应答用 `--file`（UTF-8 无 BOM），ASCII 可用 `--text`；完成对归档至 `bridge/done/`，请求端默认等待 30 分钟（`FATE_BRIDGE_TIMEOUT`）。
- 修复 `novelborne-3.0.1/core/app.py` 基础/简单模式两阶段开局：开局核对清单按 rounds_rule/opening_check 契约不含选项，on_start 以 opening 阶段提交并保留“确认开局”输入框（顶层与 opening_state 嵌套标志同步置否），玩家确认后首幕与 A–F 选项正式提交时视为开局确认完成、恢复常规选项与自由输入。
- 桥模式下 AI 配置页两按钮接管（前端零改动）：`fetch_models` 返回 `skill-bridge-assistant` 占位、`/api/models/fetch` 附带“skill 桥已接管”消息；`test_connection` 直接返回成功说明，不再发真实探测请求、不再产生 ping 桥任务；`SkillBridgeClient` 补 `models.list()` 兜底防裸 AttributeError。
- 移除 2.1.0 的自定义只读驾驶舱（`scripts/ui.py`、`scripts/test_ui.py`、`assets/ui/`）：GUI 统一为原版 NovelBorne 界面 + 文件桥，界面上未实现或未做好的功能属于 skill 的修复范围。
- 以零凭据完成浏览器端到端实测：上传→确定人物与难度设定→生成推荐金手指（确定性推荐）→开局核对（角色安排师 JSON + 清单正文）→确认开局→首幕 + 选项生成卷 JSON→选项点击→回合 2，均经 GUI DOM 与 `/api/sessions/{id}/state` 双重验证。

### 文档

- SKILL.md 改写：GUI 桥模式为默认工作流（启动命令、桥循环、各类任务应答格式、边界），CLI 会话模式保留为无浏览器备选。
- references/runtime-api.md 新增 §8 GUI 桥命令；README、FEATURE-MAP、MANIFEST 同步 2.2.0。

## 2.1.0 — 2026-09-17

### 只读驾驶舱（新增可选 GUI）

- 新增 `scripts/ui.py`：标准库本地 HTTP 服务（默认仅 127.0.0.1），启动打印带随机 token 的访问地址；`--workspace` 指向包含 `novelborne-data/` 的工作区。
- 仅暴露只读端点：`/api/health`、`/api/sessions`、`/api/status`、`/api/doctor`、`/api/render` 与三个静态页面。没有任何写入端点（POST/PUT/DELETE/PATCH 一律 405），不提供 input/commit/确认等入口；GUI 不发送、不确认、不代替用户。
- 访问控制：token 常量时间比较、Host/Origin 校验阻挡其他网页的跨站请求；会话名白名单字符 + 目录包含检查；CSP `default-src 'none'`。
- 浏览器子资源认证：浏览器无法为 `<script>/<link>` 附加自定义头，首次带 token 的请求会下发 `HttpOnly; SameSite=Strict; Path=/` 的同名 cookie（仅当主动出示有效 token 时），之后每个请求仍需凭 header/query/cookie 之一通过校验；cookie 对页面脚本不可读，跨站请求被 SameSite 阻断。
- 与助手 CLI 共享同一会话互斥锁；`session_busy_or_stale_lock` 短退避重试（约2秒），轮询不因正在进行的交易而永久失败。损坏/未知目录在列表中标记不可读，不影响其他会话。
- 新增 `assets/ui/`（无构建、无外部依赖、无内联脚本）：对局状态与章内预算、准备覆盖进度条（按回执区间并集）、确认与人物卡清单、doctor 下一步与当前确认门高亮、已提交正文阅读视图（首字下沉、章题识别、按距离渐隐；仅 commit 后内容）、A–F 选项与 `选择：/行动：/规则：/问答：/增补：/控制/确认门/存档/导出` 规范消息一键复制、三套主题与 5 秒轮询。
- 新增 `test_ui.py`：真实签名对局 + 真实 HTTP 请求的 31 项测试（访问控制、只读保证、路径包含、坏会话、并发读、各端点载荷、确认门提示、cookie 签发与子资源授权/错误 cookie/畸形头拒绝）。全仓 137 项测试通过；另以真实浏览器完成纸墨/夜航双主题冒烟（数据加载、三栏布局、首字下沉、距离渐隐、A–F 选项与复制区均验证）。

## 2.0.0 — 2026-09-15

### 工作流与门禁

- create 提前到来源准备与确认之前；建局后每条用户消息走 `input --text-file`，未知文字澄清，不猜测自由行动或自动纠正小写选项。
- 增加每窗最多2000字符的来源回执、逐字引用产物及客观区间并集进度；强化必须 fullbook，禁止非空 semantic_coverage 自报完成。
- 分别确认设定、金手指、全体人物、开局；完整 rich card 包含决策/口吻/行为边界，来源姓名需有已接受引用证据，知识按起点截止。
- 开局前 revise 重校验并重置确认/卡片，保留已有来源回执与产物。
- 正文统一 context→plan→stage→review→commit→render；token/revision/hash 绑定，改写须 context --fresh 全链重走；最终展示已提交 render，不另生成正文。
- 原正文档目标新增 ±25% Unicode 字符范围，六选项保持 A–F、4剧情+2性格并归一化去重。

### 计算、审计与工具

- 涟漪、K和动态收束计算随 commit 持久化；plan 必填 resolution，涟漪拒绝不能配 success。
- 当前章已接受锚点在预算最后回合/翻章前需 fulfilled/hint_only disposition；保留证据说明及候选审计记录，不声称语义验证。
- doctor 给下一步与阻碍；template 只输出当前数据骨架，需助手补齐真实内容并执行，不自动确认或修复。
- 双码原值与固定权限不变；永久通路下跳过锚点并允许 anchors=[] 的 facts-only准备，以补后续章来源。

### 兼容与诚实边界

- 1.0 session 在 v2 仅查看/导出，不静默迁移。继续旧局应手动使用原样保留的 v1 分发包；新局走v2确认。
- checkpoint 仍是审计副本，没有回滚/导入；小说导出不是可恢复存档。
- README 增加中文优先与英文说明；文档明确无独立外部蒸馏/审稿调用、无需新API key、产物语义未验证。资源、冷却、任务未全部自动化，数值检查不等于完整因果/人物逻辑保证。
- 验证范围与最终结果：**see evals/RESULTS.md**。不以历史测试数量或程序测试替代真实宿主多轮验收。

## 1.0.0

初始本地 skill 适配：文本索引、参数协商、双码、签名状态、六选项提交、原公式只读包装与故事导出。旧包按原样保留供显式兼容使用，不回写成v2或静默迁移旧局。
