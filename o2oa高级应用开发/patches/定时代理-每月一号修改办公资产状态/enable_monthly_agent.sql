-- 启用「每月一号修改办公资产状态」定时代理（幂等，可重复执行）
-- 执行：docker exec o2oa-mysql sh -c 'mysql -uo2oa -po2oa_pwd X < enable_monthly_agent.sql'

UPDATE CTE_AGENT
   SET xenable = 1, xupdateTime = NOW()
 WHERE xid = '7e78ba01-e2bf-402b-badf-f706d7888119';

-- 可选：把频率从"每月1号每30分钟"改为"每月1号01:00一次"（取消下一行注释即生效）
-- UPDATE CTE_AGENT SET xcron = '0 0 1 * * ?', xupdateTime = NOW()
--  WHERE xid = '7e78ba01-e2bf-402b-badf-f706d7888119';

SELECT xid, xname, xenable+0 AS enable, xcron, xlastStartTime, xlastEndTime
  FROM CTE_AGENT;
