# 🎮 NovelBorne Interactive Story Skill  
# 🎮 NovelBorne 互动小说技能

> **English** · A local-first interactive story-engine skill for ZCode, adapted from NovelBorne 3.0.1.  
> **中文** · 一个面向 ZCode 的本地优先互动小说引擎技能，改编自 NovelBorne 3.0.1。

[![License: AGPL v3+](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![Runtime](https://img.shields.io/badge/Runtime-Python%203.10%2B-3776AB.svg)](scripts/runtime.py)
[![Tests](https://img.shields.io/badge/Tests-54%20passed-2EA44F.svg)](evals/RESULTS.md)
[![Mode](https://img.shields.io/badge/Mode-Local--first-8B5CF6.svg)](SKILL.md)

---

## ✨ Overview / 概览

**English**  
NovelBorne transforms a user-provided novel or source text into a controlled interactive-story session. It keeps the story workflow explicit, local, and auditable: prepare the source, negotiate settings, confirm the opening, then commit narrative turns and choices.

**中文**  
NovelBorne 将用户提供的小说或文本转换为受控的互动故事会话。流程保持明确、本地化且可审计：准备文本、协商参数、确认开局，再逐回合提交剧情与选项。

```text
📄 Source text
      │
      ▼
⚙️ Parameter negotiation
      │
      ▼
✅ Explicit opening confirmation
      │
      ▼
📖 Narrative turn + choices
      │
      ▼
🔐 Signed local story ledger
```

---

## 🧭 What It Does / 功能说明

| Icon | English | 中文 |
| :--: | --- | --- |
| 📥 | Accepts a user-provided source text and indexes it safely. | 接收用户提供的文本并安全建立索引。 |
| ⚙️ | Negotiates story mode, protagonist, difficulty, convergence, companions, and golden-finger settings. | 协商故事模式、主角、难度、收束、同伴与金手指等参数。 |
| 🛑 | Requires an explicit start confirmation before the opening scene is generated. | 在生成开篇前要求用户明确确认开局。 |
| 📖 | Produces narrative turns with strictly ordered A–F choices. | 生成带严格 A–F 排序选项的剧情回合。 |
| 🔐 | Stores state in signed, revisioned local session envelopes. | 使用带签名和版本号的本地会话封装保存状态。 |
| 🧠 | Preserves the original engine’s two dedicated cheat-code mechanisms. | 保留原引擎的两套专属作弊码机制。 |
| 🛡️ | Treats text and model output as untrusted data rather than instructions. | 将文本和模型输出视为不可信数据，而非指令。 |
| 🎭 | Includes trope search and nine deterministic narrative personality styles. | 包含桥段检索与九种确定性叙事人格风格。 |

---

## 🌟 Highlights / 核心特性

### 🔒 Secure-by-Design / 安全优先

- **English:** Source files, player text, narrative facts, and model output are handled as data only—never executable instructions.
- **中文：** 原文、玩家输入、剧情事实和模型输出都只会作为数据处理，绝不作为可执行指令。

- **English:** Protected configuration and mechanism fields cannot be changed through ordinary narrative text.
- **中文：** 受保护的配置和机制字段无法通过普通剧情文本篡改。

- **English:** Cheat codes are accepted only through the dedicated Q&A pathway with exact-match routing; no alternate cheat route is exposed.
- **中文：** 作弊码仅可通过专用问答通道以精确匹配方式触发，不提供其他作弊入口。

- **English:** Session state uses HMAC signatures, revision checks, atomic replacement, and lock files.
- **中文：** 会话状态采用 HMAC 签名、版本校验、原子替换与锁文件机制。

> ⚠️ **Security boundary / 安全边界**  
> HMAC protects against accidental modification and tampering without the local key. It does not protect against a local attacker who can read the session key or replace signed snapshots.  
> HMAC 可以防止意外修改以及未持有本地密钥时的篡改；但无法防御能读取会话密钥或替换已签名快照的本地攻击者。

### 🎲 Faithful Mechanics / 忠实机制适配

- 🌊 Ripple impact and momentum / 涟漪影响与积势
- 🧩 Compatibility K score / 兼容度 K 值
- ⚔️ Faction and nemesis difficulty / 阵营与宿敌难度
- ✨ Golden-finger scaling / 金手指强度缩放
- 🌀 Dynamic convergence / 动态收束
- ⚓ Tasks and normal-anchor breaking / 任务与常规锚点破碎
- 🎭 Nine personality styles / 九种人格风格
- 📚 Trope retrieval across five genres / 五类题材桥段检索

### 📚 Bundled Trope Library / 内置桥段库

The included trope library contains **3,409 entries**:

内置桥段库包含 **3,409 条** 数据：

| 💼 Business | ⚔️ Combat | 🏠 Life | 🔍 Mystery | 💞 Romance |
| --- | --- | --- | --- | --- |
| 商业 | 战斗 | 日常 | 悬疑 | 恋爱 |

---

## 🚀 Quick Start / 快速开始

### 1. Install the skill / 安装技能

Place this repository at the following ZCode workspace location:

将本仓库放入 ZCode 工作区的以下位置：

```text
.agents/skills/novelborne/
```

### 2. Start a story / 发起故事

Use a request such as:

可使用类似请求：

```text
Use NovelBorne to turn this text into an interactive story.
```

```text
使用 NovelBorne 将这段文本转换为互动小说。
```

### 3. Follow the confirmed flow / 按确认流程游玩

```text
📄 Provide text / 提供原文
        ↓
⚙️ Confirm parameters / 确认参数
        ↓
✅ Confirm opening / 确认开局
        ↓
📖 Receive scene and choices / 获得剧情与选项
        ↓
🎲 Choose an action / 选择行动
        ↓
🔁 Continue the story / 继续故事
```

> 🛑 **No opening scene is generated before explicit opening confirmation.**  
> 🛑 **未得到明确开局确认前，不会生成开篇剧情。**

---

## 🗂️ Project Layout / 项目结构

```text
📦 novelborne/
├── 📄 SKILL.md                 # ZCode workflow / ZCode 工作流
├── 📄 FEATURE-MAP.md           # Feature preservation map / 功能映射
├── 📄 LICENSE                  # AGPL-3.0-or-later
├── 📄 NOTICE.md                # Attribution / 来源与署名
├── 📁 references/              # Documentation / 文档
│   ├── 🛡️ security.md          # Threat model / 威胁模型
│   ├── ⚙️ setup.md             # Story parameters / 参数说明
│   ├── 🎲 mechanics.md         # Game mechanics / 游戏机制
│   ├── 💻 runtime-api.md       # Runtime CLI / 运行时接口
│   └── 🧭 workflows.md         # Extended workflows / 扩展流程
├── 📁 scripts/                 # Local runtime / 本地运行时
│   ├── 🐍 runtime.py           # Story-session guard / 会话保护层
│   ├── 🐍 mechanics.py         # Read-only mechanics CLI / 只读机制接口
│   └── 📁 engine_core/         # Adapted engine core / 改编引擎核心
├── 📁 assets/data/             # Trope datasets / 桥段数据
└── 📁 evals/                   # Evaluations / 验证材料
```

---

## 🧪 Validation / 验证情况

| Test suite / 测试套件 | Count / 数量 | Result / 结果 |
| --- | ---: | :---: |
| Runtime tests / 运行时测试 | 34 | ✅ Passed |
| Mechanics tests / 机制测试 | 17 | ✅ Passed |
| Delivery tests / 交付测试 | 3 | ✅ Passed |
| **Total / 合计** | **54** | **✅ Passed** |

The full package was also tested after isolated extraction.

完整发布包也已在独立解压环境中完成测试。

---

## 🔐 Security Notes / 安全说明

- 🚫 No arbitrary code execution, import, rollback, or resume endpoint is exposed.
- 🚫 不提供任意代码执行、导入、回滚或恢复接口。

- 🧱 Source browsing is isolated from mechanism control and session authority.
- 🧱 原文浏览与机制控制、会话权限相互隔离。

- 🗝️ Never commit player-session state, `.key` files, `state.json`, lock files, or local checkpoints.
- 🗝️ 请勿提交玩家会话状态、`.key` 文件、`state.json`、锁文件或本地检查点。

Read the full threat model in [references/security.md](references/security.md).  
完整威胁模型请参阅 [references/security.md](references/security.md)。

---

## 📜 License & Attribution / 许可证与署名

This project is distributed under the **GNU Affero General Public License v3.0 or later**.

本项目基于 **GNU Affero General Public License v3.0 或更高版本** 发布。

It is adapted in part from **NovelBorne 3.0.1**. Original copyright, license, and attribution notices are retained.

本项目部分改编自 **NovelBorne 3.0.1**，并保留原项目的版权、许可证及署名声明。

- 📄 [LICENSE](LICENSE)
- 📝 [NOTICE.md](NOTICE.md)
- 🧩 [FEATURE-MAP.md](FEATURE-MAP.md)

---

## 📦 Release Package / 发布包

The packaged distribution is included as:

打包发行文件为：

```text
novelborne-skill-1.0.0.zip
```

**SHA-256**

```text
721e9dc695f9fef4fceb7239343e318e86b72669b9273bac1493dfb85094c43f
```

---

<div align="center">

**🎲 Create stories. Make choices. Keep control.**  
**🎲 创造故事，自主选择，始终掌控。**

</div>
