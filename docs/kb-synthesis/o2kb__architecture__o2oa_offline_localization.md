# 断云O2OA本地化部署定位

> category: o2kb::architecture  |  id: o2kb::architecture::o2oa_offline_localization

本机是 O2OA 社区版 10.0.2 断云（已断 collect.o2oa.net / app.o2oa.net / apppack）的「商业版平替」部署：

组织与账号：顶层组织中国复合材料工业协会；真实业务管理员 admin/o2oaadmin2026；虚拟 xadmin 同密码、tokenType=manager，但不在 ORG_PERSON、无 identity，不能当业务人员（却适合做批量运维改人）。

AI 全程不连云：推理走本地 LM Studio qwen3.8-27b @1234；向量 qwen3-embed @8089；OCR 用 RapidOCR 独立进程；网关端口 18790。

断云影响与对策：
- 应用市场/在线打包不可用 → 改离线 xapp 导入（setup.json + xapp zip）
- collect 上报失败 → 数据已落库可忽略
- express 注册查找偶发 randomWithWeight 错误 → docker restart o2oa-server 即愈（但需 5-8 分钟且重跑 o2oa_netlock.sh）
- 短信/邮件验证码已本地化（mailservice/ 平替 x_sms_assemble_control）

自建模块平替内置合同/业务/人力资源/公文/财务/资产管理等门户，要求打通底层数据层、真实渲染行数据，杜绝空壳或二级链接。
