# 来源、修改与许可证

本 skill 派生自用户提供的 `novelborne-3.0.1.zip`（NovelBorne / 书中行命运引擎 3.0.1）。上游声明 AGPL-3.0-or-later，完整许可见同目录 [LICENSE](LICENSE)。此派生包的规则改写、胶合脚本和测试同按 AGPL-3.0-or-later 提供，保留上游源文件既有版权与许可声明。skill 的版本2.0.0不是上游应用版本号。

首次改编：2026-09-14；v2 工作流适配：2026-09-15。

- `scripts/engine_core/{textkit,ripple,faction,golden_finger,dynamic_convergence,tropes}.py` 保留同名上游 core/engine 模块。
- `assets/data/tropes_*.json` 保留上游五领域桥段数据及其来源信息。
- `scripts/runtime.py` 是本地运行时适配。双码常量、确认词、次数、通路顺序和机制过滤来自上游 cheat_code.py / ask_service.py / directives_service.py，新增严格schema、签名、原子事务与v2提交门禁；并非原应用原样运行。
- `scripts/mechanics.py` 是新增白名单只读计算器/检索包装，不启动上游UI或API。
- v2 的 `preparation.py`、`interaction.py`、`turns.py`、`guidance.py` 分别适配来源回执/卡片与确认、保守消息路由、绑定候选的叙事流水线、只读诊断/数据骨架。来源产物与审稿说明由当前助手撰写，未调用独立外部蒸馏/审稿模型。
- `SKILL.md`、README 与 references 将原交互、规则、提示和代码改写为本地对话工作流；实现差异与限制见 [FEATURE-MAP.md](FEATURE-MAP.md)，v2变化见 [CHANGELOG.md](CHANGELOG.md)。

此分发不包含用户小说、正式局存档、密钥或私有资料。软件许可证不替用户取得上传文本的版权；使用者应具备相应使用权。测试用短篇为本次改编编写。完整许可证条款以 LICENSE 为准。
