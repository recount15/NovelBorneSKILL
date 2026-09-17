# v2.2.0 验证记录 / Verification record

日期：2026-09-17。

## 已执行 / Executed

工作区根目录：

```text
python -X utf8 -m unittest discover -s .agents/skills/novelborne/scripts -p "test_*.py" -v
```

**106 项全部通过。** 本轮完整运行耗时46.412秒；后续测试运行时长会随机器变化。

| 测试套件 | 数量 | 实际覆盖 |
| --- | ---: | --- |
| runtime | 34 | 原有解码/签名/锁/三愿/永久通路/注入/提交/导出回归，改为经过真实v2门禁 |
| mechanics | 17 | 原公式、资产、3409条桥段、阈值、类型、只读CLI和来源逐字对照 |
| preparation | 24 | 精确引文与来源指纹、伪造回执、区间缺口与重叠、角色结构/来源/知识、确认顺序、证据复用 |
| turns | 17 | token/revision/hash阶段门禁、错误/拒绝复核、原文变更、长度/选项、公式提交、章预算与锚点处置 |
| interaction | 11 | 普通话语/问题不推进、明确自由行动、取消pending、暂停续局、规则问答与作弊隔离、配置修改与v1只读 |
| delivery | 3 | 两回合完整subprocess CLI、doctor/template、跳步失败、render/checkpoint/export、元数据和不泄露码 |

测试在临时目录中创建测试局，不使用正式玩家数据。不调用外网、模型API或原网页应用。不通过伪造签名/绕过准备门禁让正常流程测试通过；故障注入测试仅用于验证失败原子性。

## v2.2.0：原版 GUI 桥（真实回路验收）

- `FATE_SKILL_BRIDGE=1` 下启动原版 NovelBorne 3.0.1 界面（127.0.0.1:21560，前端零改动），模型请求落盘为 `var/bridge/jobs/*.request.json`，用 `runtime.py bridge-pending / bridge-show / bridge-respond` 完成应答。桥命令本身未新增单元测试；以下真实浏览器端到端验收覆盖其行为（落盘格式、--wait 轮询、--file 中文应答、完成对归档、应答后前端继续）。
- 零 API key、零“AI 配置”完整对局实测（2026-09-17，本机 Chromium）：上传测试小说→确定人物与难度设定→生成推荐金手指（确定性推荐）→开局（角色安排师 JSON 桥任务→开局核对清单正文桥任务，opening 阶段提交、“确认开局”输入框出现、正式状态版本 1）→点击确认开局→首幕正文 + 选项生成卷 JSON 桥任务（committed、6 张 A–F 选项卡、输入框恢复）→点击选项 A→回合 2 桥任务→committed。每步经 GUI DOM 与 `/api/sessions/{id}/state` API 双重验证。
- 修复 `novelborne-3.0.1/core/app.py` 基础/简单模式两阶段开局（原版潜在缺陷，与桥无关也会触发）：开局核对清单不含选项时不再报“开局未生成完整 A-F 选项”，改为 opening 阶段提交并同步置否顶层与 `opening_state` 嵌套的 `opening_confirmed`；首幕与选项正式提交时视为开局确认完成。
- 2.1.0 自定义只读驾驶舱（`scripts/ui.py`、`scripts/test_ui.py`、`assets/ui/`）已移除，其 31 项测试随之移除（137→106）。
- 桥模式下 AI 配置页两按钮实测（2026-09-17，浏览器点击）：「拉取」后模型下拉变为 `skill-bridge-assistant` 并显示绿色“skill 桥已接管：模型调用由宿主 Agent 应答，无需配置 API Key”；「测试」显示绿色“连接成功：skill 桥已接管…”；两次点击均未在 `var/bridge/jobs/` 产生桥任务。界面其余部分（提供商/密钥/思考模式等）在桥模式下为摆设，不影响对局。

## v2.1.0 记录（驾驶舱已移除，保留历史）

- 新增只读驾驶舱（`scripts/ui.py` + `assets/ui/`）：仅 status/doctor/render 与会话列表；写入方法一律405；token 常量时间比较；CSP `default-src 'none'`；与 CLI 共享会话锁并在忙锁时短退避重试。
- 浏览器子资源 403 缺陷发现并修复：浏览器不能为 `<script>/<link>` 附加自定义头，导致 app.js/style.css 被拒。修复为仅在主动出示有效 token 的请求上签发 `HttpOnly; SameSite=Strict` cookie，每个请求仍需 header/query/cookie 之一通过校验；页面脚本读不到该 cookie，跨站发送被 SameSite 阻断。含5项回归测试。
- 真实浏览器冒烟（2026-09-17）：cookie 修复后子资源全部 200；会话列表、状态卡、doctor、两幕正文渲染、A–F 选项卡与复制区、纸墨/夜航双主题均验证。该 UI 在 2.2.0 已被原版界面 + 文件桥取代。

### v2.0.0 记录（保留）

- 已删除自报semantic_coverage通过路径；覆盖由已发窗口与已接受引文产物区间并集计算。
- 新增角色必填维度与人数、名字/来源匹配，原著引文与人物知识分离。
- 未知无前缀文字不再直接接受为行动。
- 草稿提交必须引用同一份已stage、review的候选；复核拒绝不可用第二份空issues覆盖。
- 公式结果在commit时持久化，失败草稿不扣回合或累加结果。
- 修复CLI运行时模块双重导入导致异常类型不一致的隐患；错误命令返回固定JSON错误。

## 不证明的事项 / Not established

**未在全新宿主对话中完成由真人逐步确认的长篇多轮验收。** cases.md列出待测模型场景，不声称这些已由独立模型运行。GUI 桥已通过单机真实浏览器端到端验收（上传→开局→两回合，含桥应答真实落盘/归档），但不等价于真人长篇多轮玩法验收，也未覆盖暂停/续局、翻章、导出等界面功能在桥模式下的逐一实机验证。

没有调用独立外部蒸馏器或审稿模型。引用校验是真实字符比较，覆盖是真实区间计算，但summary/claim、角色语义、锚点处置理由和review结论仍由当前助手撰写；桥模式下正文、选项、人物安排的内容质量同样由应答的助手负责。程序不能证明它理解了全部来源、没有同章剧透、资源叙事始终连续，或完全服从skill。若宿主助手绕过工具直接输出文本，单独skill不能拦截那个聊天输出。文件桥仅限本机目录读写，不防能读取进程输出或本机文件者。

输入过滤不是普遍的语义安全证明。HMAC不防有密钥/程序/整个目录控制权的本机攻击者。完整任务、资源、金手指冷却业务引擎与原应用多模型DAG没有全部移植。1.0.0旧局未自动迁移；原v1 ZIP原样保留。

English: All 106 automated tests passed in the working tree. They verify local structural and transaction gates for the CLI session mode. The original-GUI bridge mode was verified by a real single-machine browser end-to-end run (upload → setup → opening checklist → confirm → first scene with options → option click → round 2, zero credentials, jobs answered via the bridge CLI); this does not establish live host-model adherence over long human-supervised sessions, independent semantic review, or complete upstream parity of every UI feature under the bridge.
