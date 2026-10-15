package com.x.message.assemble.communicate.jaxrs.im;

import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Optional;

import javax.imageio.ImageIO;

import org.apache.commons.lang3.ArrayUtils;
import org.apache.commons.lang3.math.NumberUtils;
import org.imgscalr.Scalr;

import com.x.base.core.container.EntityManagerContainer;
import com.x.base.core.container.factory.EntityManagerContainerFactory;
import com.x.base.core.project.cache.Cache.CacheCategory;
import com.x.base.core.project.cache.Cache.CacheKey;
import com.x.base.core.project.cache.CacheManager;
import com.x.base.core.project.config.StorageMapping;
import com.x.base.core.project.http.ActionResult;
import com.x.base.core.project.http.EffectivePerson;
import com.x.base.core.project.jaxrs.WoFile;
import com.x.base.core.project.logger.Logger;
import com.x.base.core.project.logger.LoggerFactory;
import com.x.message.assemble.communicate.ThisApplication;
import com.x.message.core.entity.IMMsgFile;

/**
 * Created by fancyLou on 2020-06-15. Copyright © 2020 O2. All rights reserved.
 */
public class ActionImageDownloadWidthHeight extends BaseAction {

	private static final Logger LOGGER = LoggerFactory.getLogger(ActionImageDownloadWidthHeight.class);

	private static String[] imageExtentionArray = new String[] { "jpg", "png", "bmp", "jpeg" };
	ActionResult<Wo> execute(EffectivePerson effectivePerson, String id, Integer width, Integer height)
			throws Exception {

		LOGGER.debug("execute:{}, id:{}, width:{}, height:{}.", effectivePerson::getDistinguishedName, () -> id,
				() -> width, () -> height);

		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			ActionResult<Wo> result = new ActionResult<>();
			Wo wo = null;
			/** 确定是否要用application/octet-stream输出 */
			IMMsgFile file = emc.find(id, IMMsgFile.class);
			if (null == file) {
				throw new ExceptionFileNotExist(id);
			}
			if (!ArrayUtils.contains(imageExtentionArray, file.getExtension().toLowerCase())) {
				throw new IllegalStateException("file is not image file.");
			}
			if (width < 0 || width > 5000) {
				throw new IllegalStateException("invalid width:" + width + ".");
			}
			if (height < 0 || height > 5000) {
				throw new IllegalStateException("invalid height:" + height + ".");
			}

			CacheCategory cacheCategory = new CacheCategory(ActionImageDownloadWidthHeight.class);
			CacheKey cacheKey = new CacheKey(this.getClass(), id + width + height);

			Optional<?> optional = CacheManager.get(cacheCategory, cacheKey);

			if (optional.isPresent()) {
				wo = (Wo) optional.get();
				result.setData(wo);
			} else {
				StorageMapping mapping = ThisApplication.context().storageMappings().get(IMMsgFile.class,
						file.getStorage());
				if (null == mapping) {
					throw new ExceptionStorageNotExist(file.getStorage());
				}
				byte[] raw = this.readContentWithRetry(file, mapping);
				try {
					ByteArrayInputStream input = new ByteArrayInputStream(raw);
					BufferedImage src = ImageIO.read(input);
					int scalrWidth = (width == 0) ? src.getWidth() : width;
					int scalrHeight = (height == 0) ? src.getHeight() : height;
					Scalr.Mode mode = Scalr.Mode.FIT_TO_WIDTH;
					if (src.getWidth() > src.getHeight()) {
						mode = Scalr.Mode.FIT_TO_HEIGHT;
					}
					BufferedImage scalrImage = Scalr.resize(src, Scalr.Method.SPEED, mode,
							NumberUtils.min(scalrWidth, src.getWidth()),
							NumberUtils.min(scalrHeight, src.getHeight()));
					try (org.apache.commons.io.output.ByteArrayOutputStream baos = new org.apache.commons.io.output.ByteArrayOutputStream()) {
						ImageIO.write(scalrImage, "png", baos);
						byte[] bs = baos.toByteArray();
						wo = new Wo(bs, this.contentType(false, file.getName()),
								this.contentDisposition(false, file.getName()));
						CacheManager.put(cacheCategory, cacheKey, wo);
						result.setData(wo);
					}
				} catch (Exception ex) { // 图片转化异常的情况 直接返回整个文件
					LOGGER.warn("图片转化异常", ex);
					byte[] bs = raw;
					wo = new Wo(bs, this.contentType(false, file.getName()),
							this.contentDisposition(false, file.getName()));
					// 对10M以下的文件进行缓存
					if (bs.length < (1024 * 1024 * 10)) {
						CacheManager.put(cacheCategory, cacheKey, wo);
					}
					result.setData(wo);
				}
			}
			return result;
		}
	}

	/** 读取重试次数（瞬时读不到 ≠ 文件不存在） */
	private static final int READ_RETRY = 4;
	/** 读取重试退避基数（毫秒），第 n 次等待 READ_RETRY_INTERVAL_MS * n */
	private static final long READ_RETRY_INTERVAL_MS = 300L;

	/**
	 * 读取图片原始字节，带短退避重试。
	 *
	 * ★★ 2026-10-15 修复（本实例实证，「发出去的图片过一会儿就打不开」根因）：
	 *   旧实现在读取失败、且异常消息包含 "existed" 时，会执行
	 *     emc.delete(IMMsgFile.class, file.getId()) —— 把「瞬时读不到」
	 *   直接升级成「元数据永久消失」。
	 *   而上传侧原本是「先写库、后异步落盘」，前端拿到 id 后立刻请求缩略图，
	 *   极易抢在字节落盘之前 → 必然判 "not existed" → 记录被删、字节随后才写成功
	 *   ⇒ 物理文件完好，记录没了，该消息此后永远 500，且会反复复发。
	 *   （实测 out.log：upload 与 "不存在，删除记录" 同秒，间隔约 30ms）
	 *
	 *   现在：只重试 + 只留痕，【绝不触碰元数据】。
	 *   元数据是持久事实，存储抖动是瞬时现象，二者不可互相推断；
	 *   即便真的丢了文件，也应保留记录交由运维决定，而不是由一次读失败自动销毁。
	 */
	private byte[] readContentWithRetry(IMMsgFile file, StorageMapping mapping) throws Exception {
		Exception last = null;
		for (int attempt = 1; attempt <= READ_RETRY; attempt++) {
			try (ByteArrayOutputStream os = new ByteArrayOutputStream()) {
				file.readContent(mapping, os);
				return os.toByteArray();
			} catch (Exception e) {
				last = e;
				if (attempt < READ_RETRY) {
					try {
						Thread.sleep(READ_RETRY_INTERVAL_MS * attempt);
					} catch (InterruptedException ie) {
						Thread.currentThread().interrupt();
						break;
					}
				}
			}
		}
		LOGGER.warn("聊聊图片读取失败（已重试{}次，保留记录待存储恢复，交由前端重试）: id={}, name={}, storage={}, err={}",
				READ_RETRY, file.getId(), file.getName(), file.getStorage(),
				last == null ? "" : last.getMessage());
		if (null != last) {
			throw last;
		}
		throw new ExceptionFileNotExist(file.getId());
	}

	public static class Wo extends WoFile {

		private static final long serialVersionUID = -275816509098883542L;

		public Wo(byte[] bytes, String contentType, String contentDisposition) {
			super(bytes, contentType, contentDisposition);
		}

	}
}
