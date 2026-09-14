# 来源、修改与许可证

本skill派生自用户提供的 `novelborne-3.0.1.zip`（NovelBorne / 书中行命运引擎 3.0.1）。原项目声明 AGPL-3.0-or-later，完整许可见同目录 LICENSE。此派生包中的规则改写、胶合脚本和测试同按 AGPL-3.0-or-later 提供；保留上游源文件已有声明。

改编日期：2026-09-14。

- `scripts/engine_core/textkit.py,ripple.py,faction.py,golden_finger.py,dynamic_convergence.py,tropes.py`：从同名上游core/engine文件保留。
- `assets/data/tropes_*.json`：保留上游五领域桥段及manifest，共3409条。
- `scripts/runtime.py`：新离线对话运行时，作弊码常量、确认词、次数、通路顺序及机制过滤源于上游cheat_code.py / ask_service.py / directives_service.py；增加严格schema、签名和原子提交，非原应用原样运行。
- `scripts/mechanics.py`：新增白名单计算器包装及只读检索，不启动上游UI或API。
- `SKILL.md`与references：将上游交互、规则、提示及代码行为改写为对话工作流；差异见FEATURE-MAP.md。

此分发不包含用户小说、生成的正式局存档、密钥或私有素材。原项目许可不替用户上传文本取得版权；使用者应具备相应使用权。测试用短篇由本次改编新写。
