package com.x.message.assemble.communicate.jaxrs.im;

import com.x.base.core.container.EntityManagerContainer;
import com.x.base.core.container.factory.EntityManagerContainerFactory;
import com.x.base.core.entity.annotation.CheckPersistType;
import com.x.base.core.project.annotation.FieldDescribe;
import com.x.base.core.project.config.StorageMapping;
import com.x.base.core.project.http.ActionResult;
import com.x.base.core.project.http.EffectivePerson;
import com.x.base.core.project.jaxrs.WoId;
import com.x.base.core.project.logger.Logger;
import com.x.base.core.project.logger.LoggerFactory;
import com.x.base.core.project.tools.FileTools;
import com.x.message.assemble.communicate.ThisApplication;
import com.x.message.core.entity.IMMsgFile;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.util.Date;
import java.util.Objects;
import org.apache.commons.io.FilenameUtils;
import org.apache.commons.lang3.StringUtils;
import org.glassfish.jersey.media.multipart.FormDataBodyPart;
import org.glassfish.jersey.media.multipart.FormDataContentDisposition;

/**
 * Created by fancyLou on 2020-06-15. Copyright © 2020 O2. All rights reserved.
 */
public class ActionUploadFile extends BaseAction {

	private static final Logger LOGGER = LoggerFactory.getLogger(ActionUploadFile.class);
	public ActionResult<Wo> execute(EffectivePerson effectivePerson, String conversationId, String type,
			String fileName,  FormDataBodyPart filePart) throws Exception {

		LOGGER.debug("execute:{}, conversationId:{}, type:{}, fileName:{}.", effectivePerson::getDistinguishedName,
				() -> conversationId, () -> type, () -> Objects.toString(fileName));
		ActionResult<Wo> result = new ActionResult<>();
		StorageMapping mapping = ThisApplication.context().storageMappings().random(IMMsgFile.class);
		if (null == mapping) {
			throw new ExceptionAllocateStorageMaaping();
		}
		final File file = filePart.getValueAs(File.class);
		final Wo wo = new Wo();
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			String name = fileName;
			if (StringUtils.isEmpty(name)) {
				name = this.fileName(filePart.getFormDataContentDisposition());
			}
			name = FilenameUtils.getName(name);
			if (StringUtils.isEmpty(name)) {
				throw new ExceptionFileNameEmpty();
			}
			if (StringUtils.isEmpty(FilenameUtils.getExtension(name))) {
				throw new ExceptionEmptyExtension(name);
			}
			FileTools.verifyConstraint(1, name, null);

			IMMsgFile imMsgFile = new IMMsgFile();
			imMsgFile.setName(name);
			imMsgFile.setStorage(mapping.getName());
			imMsgFile.setPerson(effectivePerson.getDistinguishedName());
			Date now = new Date();
			imMsgFile.setCreateTime(now);
			imMsgFile.setLastUpdateTime(now);
			imMsgFile.setExtension(StringUtils.lowerCase(FilenameUtils.getExtension(name)));
			imMsgFile.setConversationId(conversationId);
			imMsgFile.setType(type);

			/*
			 * ★★ 2026-10-15 修复「发出去的图片/文件对方打不开」（本实例实证）。
			 *
			 * 旧实现：先 persist 记录并 commit，随即把文件字节交给
			 *   CompletableFuture.runAsync(...) 异步落盘，接口立刻返回 200。
			 * 后果：前端拿到 fileId 后【立即】渲染缩略图，请求
			 *   /jaxrs/im/msg/download/{id}/image/width/{w}/height/{h}；
			 *   此刻异步写盘通常尚未完成 → 存储层 resolveFile 判定
			 *   "not existed" → 触发 ActionImageDownloadWidthHeight 里
			 *   「读到不存在就删记录」的分支，IMMsgFile 记录被永久删除，
			 *   而字节随后才写成功。⇒ 物理文件完好、记录没了 ⇒ 该消息此后
			 *   永远 500（ImAction 抛 ExceptionFileNotExist），表现为
			 *   「有人发图给我，我点开是坏的；过一阵自己就好了」反复出现。
			 *   （实测日志：upload 与 WARN "不存在，删除记录" 同秒，间隔 ~30ms）
			 *
			 * 新实现：先同步把字节写入存储，成功后再写库并返回。
			 *   返回的 fileId 一定对应「已落盘的内容」，从根上消除该竞态；
			 *   若写盘失败则不产生任何记录（宁可上传失败可见，也不要产生
			 *   "有记录无文件"的坏消息）。
			 */
			try (InputStream input = new FileInputStream(file)) {
				imMsgFile.saveContent(mapping, input, name);
			}

			emc.check(imMsgFile, CheckPersistType.all);

			emc.beginTransaction(IMMsgFile.class);
			emc.persist(imMsgFile);
			emc.commit();

			wo.setId(imMsgFile.getId());
			wo.setFileExtension(imMsgFile.getExtension());
			wo.setFileName(name);
			result.setData(wo);

		}
		LOGGER.info("消息模块同步上传附件：{}, 大小：{}", wo.getFileName(), (file.length() / 1024)+"k");

		return result;
	}

	public static class Wo extends WoId {

		private static final long serialVersionUID = 2329781058340372108L;

		@FieldDescribe("文件扩展名")
		private String fileExtension;

		@FieldDescribe("文件名")
		private String fileName;

		public String getFileExtension() {
			return fileExtension;
		}

		public void setFileExtension(String fileExtension) {
			this.fileExtension = fileExtension;
		}

		public String getFileName() {
			return fileName;
		}

		public void setFileName(String fileName) {
			this.fileName = fileName;
		}
	}
}
