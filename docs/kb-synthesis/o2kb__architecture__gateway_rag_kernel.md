# 网关内置RAG内核复用

> category: o2kb::architecture  |  id: o2kb::architecture::gateway_rag_kernel

O2OA AI 网关 o2_agent_gateway.py 已内建 RAG 内核，无需另起向量库即可让 AI 具备本地检索学习能力：

存储：SQLite data.db
- docs 表：id, title, category, content, creator_person, creator_unit, question_enable, permission, meta
- chunks 表：doc_id, seq, text, embedding(BLOB, qwen3-embed 维度)

向量化：embed() 调 qwen3-embed @8089；检索 rag_retrieve() 带 rerank @8092 融合重排。

入库通道（推荐）：POST /idx-gateway-doc/update
- 鉴权：Authorization 头 = config.json 的 token（无 Bearer 前缀）
- body：{"id","title","category","content","permissionList":[]}
- 内部 ON CONFLICT(id) DO UPDATE 幂等 upsert，随后 reindex_doc() 自动切块+调 embed+写 chunks

分类用多层命名空间 category 字段，例如 o2oa_manual / o2oa_api / o2oa_ops / o2oa_version / ops_experience / ai_synthesis / o2kb::methodology 等。permissionList=[] 即全员可见。复用此内核即可让 AI 在对话中 RAG 本地 O2OA 资料。
