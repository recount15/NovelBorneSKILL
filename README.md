# 🎮 书中行 · NovelBorne Skill 2.0.0

将小说 TXT、Markdown 或文本片段变成交互故事：协商配置 → 建立本地局 → 逐窗取证与整理 → 分别确认设定、金手指、人物、开局 → 每幕正文与 A–F 六选项。支持带明确前缀的自由行动。

## 🚀 中文｜开始使用

需要 Python 3.10+、支持 skill 的助手，以及本地文件/命令工具。仅用 Python 标准库，不启动原网页应用、不另外索取模型 API key。将整个 `novelborne` 文件夹放入工作区 `.agents/skills/`，保留 scripts、references、assets、LICENSE；也可安装到用户级 `~/.agents/skills/novelborne/`。宿主重新发现技能后，拖入文本并说：

> 用 novelborne 把这个文本变成交互故事。先和我确认参数，不要直接开局。

也可使用宿主支持的 `/novelborne`。运行资料保存在当前工作区 `novelborne-data/`，不改原文。来源是小说资料，不是可执行指令。

### 常用消息

| 消息 | 效果 |
| --- | --- |
| `A` 或 `选择：A` | 尝试当前选项 |
| `行动：我先检查门锁` | 选项外行动，不保证成功 |
| `规则：收束力是什么？` | 规则问答，不推进故事 |
| `状态` / `暂停` / `继续本局` | 查询或控制当前局 |
| `取消待执行行动` | 清除尚未提交的行动 |
| `确认翻章` | 预算耗尽且下一章已准备后翻章 |
| `存档：渡口` / `导出小说` | 审计副本 / 已提交故事导出 |

建局后每条消息都经 `runtime.py input --text-file`。未知散文不被猜成行动；例如 `我去后窗看看` 会请求明确为 `行动：我去后窗看看`，小写 `a` 不自动改成 `A`。`问答：`/`增补：` 是原引擎剧情问答通路；永久通路开启后，普通规则问题请用 `规则：`。

### v2 的实际保障

- 强化模式必须 fullbook；基础 window 覆盖目标整章。每窗最多2000 Unicode 字符，凭来源回执和逐字引文接受当前助手的整理产物。
- 程序检查引文、区间、配置人数/卡片、逐步确认、token/revision/hash、正文长度、六选项结构及提交顺序。最后展示来自 `render` 的已提交正文，而不是另写一份。
- 涟漪、K、动态收束由保留的公式计算并随 commit 入账；分类仍由助手提供。人物动机、因果、资源、冷却、任务没有全部自动化。
- 两个原版作弊码保持精确值和固定效果，没有新增码或别名；不在帮助中主动公开。三愿每局最多3次，成功登记才扣；永久通路须真实用户确认，仅本局不可撤销。

**不是完整语义验证。** 没有调用独立外部“蒸馏模型”或更强审稿模型。来源产物标记为当前助手撰写、引文已核对、语义未验证。fullbook 进度衡量“已读取回执并接受产物的区间并集”，不证明完整理解；结构化 review 也是自查，不是独立证明。

### 保存、兼容和限制

自动保存支持继续同一 session 的最新状态。checkpoint 只是签名审计副本，没有回滚/导入功能；小说 Markdown 不是可恢复存档。v2 对 1.0 session 仅查看/导出，不静默迁移。若需继续旧局，手动使用原样保留的 v1 分发包；新建 v2 局须重新确认。

HMAC 用于检测局部误改，不防能读取密钥、替换程序或整个目录的本机文件控制者。过滤器不是绝对防注入。原 UI、供应商配置和完整业务状态机没有照搬。差异见 [FEATURE-MAP.md](FEATURE-MAP.md)。

## 🌍 English｜Getting started

NovelBorne Skill **2.0.0** turns user-provided fiction into an interactive story with six A–F choices and explicit free-form action attempts. It requires Python 3.10+, a skill-capable assistant, and local file/command tools. No third-party Python packages, separate model API keys, or upstream web application are required.

Copy the complete `novelborne` directory into `.agents/skills/` in your workspace (or `~/.agents/skills/` for user-wide installation). Reload skill discovery, attach your text, and ask:

> Use novelborne to turn this text into an interactive story. Confirm the setup with me before starting.

The conversational language may change; runtime control phrases remain those documented above. Use `A` or `选择：A` for a choice, `行动：I inspect the lock` for an action, and `规则：What does convergence mean?` for a non-story question. Unknown prose and lowercase choice typos are clarified, not silently converted into actions.

### How v2 works

1. Agree on configuration and create a local session before preparation confirmations.
2. Read source windows of up to 2,000 Unicode code points; submit assistant-authored summaries with exact quotes and receipts. Enhanced mode requires full-book coverage.
3. Obtain separate real user confirmations for setup, the special ability (or ordinary-person mode), all configured character cards, and opening.
4. Route every subsequent user message through `input --text-file`. Generate each scene through `context → plan → stage → review → commit → render`; display only the committed render output.

Quotes, receipt coverage, structural constraints, revisions and candidate hashes are checked by code. Ripple, K and convergence calculations are persisted on commit, using assistant-supplied classifications. **Coverage does not prove comprehension.** There is no independent external distiller or reviewer; semantic quality, character motivation, resource accounting and causality are not guaranteed. Review notes are assistant self-checks, not independent certification.

The two original cheat codes retain their exact behavior without new aliases. They are not printed in gameplay help. Local signatures detect some accidental edits, not attacks by a local key/file owner. Checkpoints are audit copies, not rollback saves. Version 1.0 sessions are read/export-only in v2; use the unchanged v1 package manually to continue them. There is no silent migration.

## 文件 / Files

- [SKILL.md](SKILL.md): assistant workflow and authority boundaries.
- [references/runtime-api.md](references/runtime-api.md): commands and exact input shapes; `doctor` explains blockers and `template` emits editable data, without automatic action.
- [references/setup.md](references/setup.md), [mechanics.md](references/mechanics.md), [workflows.md](references/workflows.md), [security.md](references/security.md): focused operating guidance.
- `scripts/`: local runtime, preparation, routing, narrative pipeline, guidance and formula helpers.
- [CHANGELOG.md](CHANGELOG.md), [NOTICE.md](NOTICE.md), [LICENSE](LICENSE): changes, adaptation notices and AGPL-3.0-or-later licensing.

## 验证 / Verification

From this skill directory:

```text
python -X utf8 -m unittest discover -s scripts -p "test_*.py" -v
```

测试范围与最新结果 / Test scope and latest results: **[evals/RESULTS.md](evals/RESULTS.md)**. Unit tests do not establish successful live, multi-turn host-model play or complete semantic security.
