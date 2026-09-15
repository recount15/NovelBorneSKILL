# v2.0.0 验证记录 / Verification record

日期：2026-09-15。

## 已执行 / Executed

工作区根目录：

```text
python -X utf8 -m unittest discover -s .agents/skills/novelborne/scripts -p "test_*.py" -v
```

**106 项全部通过。** 本轮完整运行耗时45.171秒；后续测试运行时长会随机器变化。

| 测试套件 | 数量 | 实际覆盖 |
| --- | ---: | --- |
| runtime | 34 | 原有解码/签名/锁/三愿/永久通路/注入/提交/导出回归，改为经过真实v2门禁 |
| mechanics | 17 | 原公式、资产、3409条桥段、阈值、类型、只读CLI和来源逐字对照 |
| preparation | 24 | 精确引文与来源指纹、伪造回执、区间缺口与重叠、角色结构/来源/知识、确认顺序、证据复用 |
| turns | 17 | token/revision/hash阶段门禁、错误/拒绝复核、原文变更、长度/选项、公式提交、章预算与锚点处置 |
| interaction | 11 | 普通话语/问题不推进、明确自由行动、取消pending、暂停续局、规则问答与作弊隔离、配置修改与v1只读 |
| delivery | 3 | 两回合完整subprocess CLI、doctor/template、跳步失败、render/checkpoint/export、元数据和不泄露码 |

测试在临时目录中创建测试局，不使用正式玩家数据。不调用外网、模型API或原网页应用。不通过伪造签名/绕过准备门禁让正常流程测试通过；故障注入测试仅用于验证失败原子性。

## 修复与执行性质

- 已删除自报semantic_coverage通过路径；覆盖由已发窗口与已接受引文产物区间并集计算。
- 新增角色必填维度与人数、名字/来源匹配，原著引文与人物知识分离。
- 未知无前缀文字不再直接接受为行动。
- 草稿提交必须引用同一份已stage、review的候选；复核拒绝不可用第二份空issues覆盖。
- 公式结果在commit时持久化，失败草稿不扣回合或累加结果。
- 修复CLI运行时模块双重导入导致异常类型不一致的隐患；错误命令返回固定JSON错误。

## 不证明的事项 / Not established

**未在全新宿主对话中完成由真人逐步确认的长篇多轮验收。** cases.md列出待测模型场景，不声称这些已由独立模型运行。

没有调用独立外部蒸馏器或审稿模型。引用校验是真实字符比较，覆盖是真实区间计算，但summary/claim、角色语义、锚点处置理由和review结论仍由当前助手撰写。程序不能证明它理解了全部来源、没有同章剧透、资源叙事始终连续，或完全服从skill。若宿主助手绕过工具直接输出文本，单独skill不能拦截那个聊天输出。

输入过滤不是普遍的语义安全证明。HMAC不防有密钥/程序/整个目录控制权的本机攻击者。完整任务、资源、金手指冷却业务引擎与原应用多模型DAG没有全部移植。1.0.0旧局未自动迁移；原v1 ZIP原样保留。

English: All 106 automated tests passed in the working tree. They verify local structural and transaction gates, not live host-model adherence, independent semantic review or complete upstream parity.
