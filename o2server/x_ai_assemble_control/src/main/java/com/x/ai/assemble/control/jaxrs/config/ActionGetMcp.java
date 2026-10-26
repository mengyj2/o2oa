package com.x.ai.assemble.control.jaxrs.config;

import com.x.ai.assemble.control.Business;
import com.x.ai.assemble.control.bean.AiConfig;
import com.x.ai.assemble.control.bean.McpConfig;
import com.x.base.core.entity.JpaObject;
import com.x.base.core.project.bean.NameValuePair;
import com.x.base.core.project.bean.WrapCopier;
import com.x.base.core.project.bean.WrapCopierFactory;
import com.x.base.core.project.connection.ActionResponse;
import com.x.base.core.project.connection.ConnectionAction;
import com.x.base.core.project.exception.ExceptionAccessDenied;
import com.x.base.core.project.exception.ExceptionEntityNotExist;
import com.x.base.core.project.http.ActionResult;
import com.x.base.core.project.http.ActionResult.Type;
import com.x.base.core.project.http.EffectivePerson;
import java.util.List;
import org.apache.commons.lang3.BooleanUtils;
import org.apache.commons.lang3.StringUtils;
import org.eclipse.jetty.util.UrlEncoded;

class ActionGetMcp extends BaseAction {

	ActionResult<Wo> execute(EffectivePerson effectivePerson, String id) throws Exception {

		// ★ 2026-10-27 放开只读：MCP 工具详情（模板/css/脚本）不含凭据，
		//   前端渲染 AI 回答里的工具卡片需要它。写操作（Create/Update/DeleteMcp）仍门禁。
		AiConfig aiConfig = Business.getConfig();
		if (BooleanUtils.isNotTrue(aiConfig.getO2AiEnable())
				|| StringUtils.isBlank(aiConfig.getO2AiToken()) && StringUtils.isBlank(
				aiConfig.getO2AiBaseUrl())) {
			throw new ExceptionCustom("请启用o2 AI智能体，并设置相关参数.");
		}
		ActionResult<Wo> result = new ActionResult<>();
		List<NameValuePair> heads = List.of(
				new NameValuePair("Authorization", "Bearer " + aiConfig.getO2AiToken()));
		String url =
				aiConfig.getO2AiBaseUrl() + "/ai-gateway-mcp/get/"+ UrlEncoded.encodeString(id);
		ActionResponse resp = ConnectionAction.get(url, heads);
		if(Type.success.equals(resp.getType())){
			Wo wo = resp.getData(Wo.class);
			result.setData(wo);
		}else{
			throw new ExceptionEntityNotExist(id);
		}

		return result;
	}

	public static class Wo extends McpConfig {
		static WrapCopier<McpConfig, Wo> copier = WrapCopierFactory.wo(McpConfig.class, Wo.class,
				null, JpaObject.FieldsInvisible);
	}

}
