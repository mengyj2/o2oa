package com.x.ai.assemble.control.jaxrs.config;

import com.x.ai.core.entity.AiModel;
import com.x.base.core.container.EntityManagerContainer;
import com.x.base.core.container.factory.EntityManagerContainerFactory;
import com.x.base.core.entity.JpaObject;
import com.x.base.core.project.bean.WrapCopier;
import com.x.base.core.project.bean.WrapCopierFactory;
import com.x.base.core.project.exception.ExceptionAccessDenied;
import com.x.base.core.project.exception.ExceptionEntityNotExist;
import com.x.base.core.project.http.ActionResult;
import com.x.base.core.project.http.EffectivePerson;
import org.apache.commons.lang3.StringUtils;

class ActionGetModel extends BaseAction {

	ActionResult<Wo> execute(EffectivePerson effectivePerson, String id) throws Exception {

		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			// ★ 2026-10-27 放开只读：模型详情的 Wo 已排除 apiKey，普通用户可读。
			//   写操作（Create/Update/DeleteModel）仍保留管理员门禁。
			ActionResult<Wo> result = new ActionResult<>();
			AiModel aiModel = emc.find(id, AiModel.class);
			if(aiModel == null){
				throw new ExceptionEntityNotExist(id, AiModel.class);
			}
			Wo wo = Wo.copier.copy(aiModel);
			if(StringUtils.isNotBlank(wo.getApiKey())) {
				wo.setApiKey("*****");
			}
			result.setData(wo);
			return result;
		}
	}

	public static class Wo extends AiModel {
		static WrapCopier<AiModel, Wo> copier = WrapCopierFactory.wo(AiModel.class, Wo.class,
				null, JpaObject.FieldsInvisible);
	}

}
