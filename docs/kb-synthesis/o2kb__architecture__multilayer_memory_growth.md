# 多层记忆与成长感知体系

> category: o2kb::architecture  |  id: o2kb::architecture::multilayer_memory_growth

为让本地 O2OA AI 持续成长、可沉淀组织知识，构建三层能力：

一、多层记忆 taxonomy（category 命名空间）
- L0 对话上下文 → L1 ops_experience（操作经验/问题解决）→ L2 o2oa_manual/api/ops/version（说明书/接口/运维/版本）→ L3 business_process（SOP）→ L4 ai_synthesis（AI 合成结论）。

二、成长感知闭环（三工具，均在 analyst/manager 角色下）
- kb_ingest：把文档/经验持续入库 data.db
- kb_reflect(topic, confirm)：把零散经验合成为 SOP。confirm=false 只出提案（CONFIRM_REQUIRED）不写；confirm=true 落 o2kb::ai_synthesis::reflect_<timestamp>
- growth_report：读 growth_ledger 表，输出能力成长账本

三、设计态四层安全闸（让 AI 能建/改流程表单应用但有护栏）
1. 角色闸：analyst/manager 白名单（由 editable() 锚定）
2. 草稿不落地：confirm=false 只出提案，不写任何业务数据
3. 过程授权：人类在对话里确认即视为授权
4. 快照+审计+可回滚：design_op 执行前留快照，design_rollback 可回退
工具族：design_op / design_rollback（BUILTIN_TOOLS + exec_builtin 分发 + capabilities「设计态」分组）。
