# 上游与本地适配功能映射 · 2.2.0

此 skill 适配 NovelBorne 3.0.1 的文本互动体验、原数值核与双码行为，不是原应用逐行等价移植。当前助手写作，标准库脚本做门禁与部分计算。测试范围 **see evals/RESULTS.md**，不以单元测试代替真实模型玩法或语义正确性证明。

| 能力 | v2 实际实现 | 未保证/差异 |
| --- | --- | --- |
| 文本/分章/预算 | prepare，编码与hash；严格字符阈值3–9回合 | 无PDF/OCR；索引不是理解 |
| 原文准备 | create 后 source-window，每窗≤2000；回执+distill逐字引用 | 当前助手产物，无独立外部蒸馏模型调用 |
| fullbook进度 | 强化强制全书；接受产物回执的字符区间并集 | 不等于全面理解；禁止 semantic_coverage 自报 |
| 锚点提取 | chunk anchors={description,quote,start,end} | 本地适配 schema，不是上游完整多阶段抽取服务 |
| 开局 | 设定→金手指→所有卡→角色→开局真实确认 | 文本作者身份由助手维护，程序不能认证用户同意 |
| 修改设定 | preopening revise 校验并清确认/卡，保留来源证据 | 开局后配置锁定，无静默热改 |
| rich角色 | 主角/成员完整字段、语音样例/行为边界、来源姓名/引用核对 | 字段不证明心理模型有效；别名解析不支持 |
| 知识边界 | knowledge章ID截止；before不含目标章 | source_refs是叙事者身份依据；同章未来泄露仍需人工查 |
| 统一输入 | 每条消息 input --text-file；明确行动/问答/控制；unknown clarify | 不语义猜测未知 prose，小写 a 不自动选A |
| 正式故事 | context→plan→stage→review→commit→render | review是自查，不是独立审稿/更强模型 |
| 六选项/长度 | A–F、4plot+2personality、归一化去重；原目标±25%字符门 | 语义差异/动机/质量由助手负责；±25%为本地策略 |
| 行动结果 | resolution字段，涟漪拒绝则limited/failed | 不证明正文真的遵守结果；自由行动非必成功 |
| 涟漪/K/动态收束 | 原公式，状态注入难度/章进度/有效收束，commit入账 | 分类/outcome来自模型；K是文本启发式，不是因果验证 |
| 章末锚点 | anchor_updates记录fulfilled/hint_only与证据；章末/翻章检查齐全 | 证据语义未验证，不是上游全部锚点结算逻辑 |
| 阵营/GF强度/桥段 | 保留原模块+只读计算器/有限检索 | 独立调用不自动修改session |
| 资源/冷却/任务/正常碎锚 | 助手按规则维护叙事账及自查 | 未完整自动化；正常碎锚不等于可写脚本解除标志 |
| 三愿码 | 精确原值、一次武装、最多3次、成功登记才扣 | 世界事实解释仍由助手负责 |
| 永久码 | 精确原值、真实确认、本局不可撤销、多选/增补/解除锚点 | 其他机制不解除；facts-only准备可继续，不能再蒸馏锚点 |
| 长记忆 | 已提交事件/账本、审计记录、助手摘要 | 16MiB状态上限；5/10幕整理不是自动任务 |
| 存档/续局 | 签名原子状态，同session最新状态，checkpoint审计副本 | 无rollback/import；HMAC不防本机密钥/程序持有人 |
| 1.0兼容 | v2查看/导出旧局 | 不自动迁移；继续旧局手动用原样保留v1包 |
| 导出 | 已提交故事Markdown，可另做用户要求的润色副本 | 小说稿不是可恢复存档，不能替换局内render |
| doctor/template | 只读下一步/阻碍与stdout数据骨架 | 不自动取证、确认、审查或写文件；空骨架不是完成 |
| UI/供应商/API/Android | 原版 NovelBorne 3.0.1 界面以 `FATE_SKILL_BRIDGE=1` 启动 + 文件桥：模型请求落盘为 jobs，助手用 `bridge-pending/bridge-show/bridge-respond` 应答，零凭据、零“AI 配置”；基础模式两阶段开局（核对清单→确认开局→首幕+选项）已修复；另有无浏览器 CLI 会话模式 | 桥应答的内容质量由助手负责；界面功能未实现或未做好属 skill 修复范围；原供应商配置/缓存并发服务在桥模式下不需要 |
| 防注入 | 数据隔离、严格schema、控制路由、保护字段、签名 | 无绝对语义安全保证，无外部独立审查 |

## 有意差异

- 强化20伙伴/10伴侣/1宿敌配置保留；阵营计算器仍最多取双方各前三名帮手，不能把30人全部线性叠加。
- 基础也可保存同局状态。基础 window 为目标整章，不承诺任意字符小片段作为准备门。
- 原纸档目标保持，v2新增长度范围；所有模式都要求完整流水线，不只在 story_agent_mode 时检查。
- 上游供应商驱动的分块抽取、身份/丰富角色/语义调用未作为独立模型链运行。本地引用核验和卡片是适配，不宣称完整蒸馏能力等价。
- 普通涟漪使用当前 effective 收束和当前章进度；动态收束的 outcome 由模型输入、默认weight=1，未完整接入旧流程的所有语义映射。
- 保存 last_turn_audit 便于查提交来源，不将审计记录当语义真值。文档中的“铁律”永远不是真实 system prompt。

## 上游定位

相对上游包根目录：`core/engine/cheat_code.py`、`core/services/ask_service.py` 对应双码；`opening_flow.py`、`core/services/game_setup.py` 与前端配置对应开局；`core/engine/{ripple,faction,golden_finger,dynamic_convergence,tropes}.py` 对应公式/素材；`quest.py`、`break_anchor.py` 是未完整自动接入的任务/碎锚规则来源；`assets/prompts/options_gen.md` 与 `core/api/save_contract.py` 对应选项/提交设计。具体派生说明见 [NOTICE](NOTICE.md)。
