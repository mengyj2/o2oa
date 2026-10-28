package com.x.message.assemble.communicate.jaxrs.im;

import java.util.Date;

import com.x.base.core.container.EntityManagerContainer;
import com.x.base.core.container.factory.EntityManagerContainerFactory;
import com.x.base.core.entity.annotation.CheckPersistType;
import com.x.base.core.project.http.ActionResult;
import com.x.base.core.project.http.EffectivePerson;
import com.x.base.core.project.jaxrs.WoId;
import com.x.base.core.project.logger.Logger;
import com.x.base.core.project.logger.LoggerFactory;
import com.x.message.assemble.communicate.Business;
import com.x.message.core.entity.IMConversationExt;

public class ActionConversationRead extends BaseAction {

	private static final Logger LOGGER = LoggerFactory.getLogger(ActionConversationRead.class);

	ActionResult<WoId> execute(EffectivePerson effectivePerson, String conversationId) throws Exception {

		LOGGER.debug("execute:{}, conversationId:{}.", effectivePerson::getDistinguishedName, () -> conversationId);

		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			ActionResult<WoId> result = new ActionResult<>();
			Business business = new Business(emc);
			IMConversationExt ext = business.imConversationFactory()
					.getConversationExt(effectivePerson.getDistinguishedName(), conversationId);
			if (ext == null) {
				/*
				 * ★ 2026-10-29 自研修复（cnccia-custom）：标已读对「不属于自己的会话」改为幂等 no-op。
				 *
				 * 原实现：throw new ExceptionEmptyBusinessObject(conversationId + "-" + DN) ⇒ HTTP 500。
				 * 该异常只说明「当前人没有这个会话的 IMConversationExt」（EXT 行只有会话成员才有），
				 * 本质是「客户端要求在错误的对象上做一件无关紧要的事」，不是服务端故障：
				 *   ① IMV2 的 markRead 调用方本就有 .catch 只打 console.debug，500 对它毫无价值；
				 *   ② 框架层 RestActions 无条件把 5xx 弹成全局红条 ⇒ 换账号不刷新页面时，
				 *      IMV2 内存态仍指向上一账号的当前会话，心跳每分钟一弹
				 *      「无法查询到对应的业务对象！businessId: <会话id>-<DN>」（2026-10-28 实证）；
				 *   ③ 任何客户端（第三方、旧缓存页面、已退出/被移除的群）都可能对旧会话补发已读。
				 *
				 * 语义正解：给一个自己不在的会话标已读 = 无副作用 = 成功。不写库、返回 data=null。
				 * 前端配套闸门：patch/imdrive/o2im_notice_guard.js D 段（连请求都不发）。
				 */
				LOGGER.debug("skip conversation read, person not in conversation:{}, conversationId:{}.",
						effectivePerson::getDistinguishedName, () -> conversationId);
				result.setData(null);
				return result;
			}
			ext.setLastReadTime(new Date());
			emc.beginTransaction(IMConversationExt.class);
			emc.persist(ext, CheckPersistType.all);
			emc.commit();

			WoId woId = new WoId();
			woId.setId(ext.getId());
			result.setData(woId);
			return result;
		}
	}
}
