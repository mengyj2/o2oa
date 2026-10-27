package com.x.file.assemble.control.jaxrs.orgdrive;

import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import javax.persistence.EntityManager;
import javax.persistence.Query;
import javax.servlet.http.HttpServletRequest;
import javax.ws.rs.Consumes;
import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.container.AsyncResponse;
import javax.ws.rs.container.Suspended;
import javax.ws.rs.core.Context;
import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.StreamingOutput;

import org.apache.commons.lang3.StringUtils;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.x.base.core.container.EntityManagerContainer;
import com.x.base.core.container.factory.EntityManagerContainerFactory;
import com.x.base.core.project.annotation.JaxrsDescribe;
import com.x.base.core.project.config.StorageMapping;
import com.x.base.core.project.http.ActionResult;
import com.x.base.core.project.http.EffectivePerson;
import com.x.base.core.project.http.HttpMediaType;
import com.x.base.core.project.jaxrs.ResponseFactory;
import com.x.base.core.project.jaxrs.StandardJaxrsAction;
import com.x.base.core.project.jaxrs.WoId;
import com.x.base.core.project.logger.Logger;
import com.x.base.core.project.logger.LoggerFactory;
import com.x.file.assemble.control.ThisApplication;
import com.x.file.core.entity.open.OriginFile;
import com.x.file.core.entity.personal.Attachment2;
import com.x.file.core.entity.personal.Folder2;

/**
 * 企业网盘（组织盘）服务。
 *
 * <p>背景：官方 x_file_assemble_control 的目录树按 xperson 严格隔离
 * （folder2/ActionCreate 强制 person=当前人；ActionListWithFolder 与 share/ActionSaveToFolder
 * 均拒绝跨人访问），因此官方「共享」只能做只读视图，无法让多人写同一个组织目录。
 *
 * <p>本服务把「企业网盘」建设为由系统账号 xadmin 物理持有的一棵 folder2 树
 * （xadmin 代持模式已有生产先例：FILE_ATTACHMENT2 中 xperson='xadmin' 的「聊聊转存」条目），
 * 由本 Action 以服务端身份代理读写，从而实现：
 * <ul>
 * <li>投放（consign）：把个人文件/目录复制进企业盘指定目录，复用 OriginFile ⇒ 零字节拷贝；</li>
 * <li>新建目录（folder）</li>
 * <li>删除审批（delete / requests / approve）：删除不再直接执行，必须经目录创建者审批后才落库删除。</li>
 * </ul>
 *
 * <p>安全约束（服务端强校验，不依赖前端）：
 * <ul>
 * <li>投放源必须属于调用者本人（FILE_ATTACHMENT2.xperson / FILE_FOLDER2.xperson）；</li>
 * <li>目标目录必须位于企业盘根之内（祖先链回溯）；</li>
 * <li>删除只能走审批；调用者无法直接 DELETE 企业盘条目（官方 attachment2 DELETE 仅认 owner=xadmin，前端不持有该身份）；</li>
 * <li>申请人不得自批；目录创建者申请删除时，审批人取兜底名单（未配置则拒绝，避免自审自批）。</li>
 * </ul>
 *
 * <p>数据表（由部署脚本 tools/orgdrive/schema.sql 一次性创建，运行期不做 DDL）：
 * <pre>
 * O2_ORGDRIVE_CFG     (xkey, xvalue)                       配置：holder / fallbackApproverPersonList / writerPersonList
 * O2_ORGDRIVE_DIR     (xfolderId, xcreator, xcreateTime)   目录逻辑创建者（物理 owner 恒为 xadmin）
 * O2_ORGDRIVE_DEL_REQ (删除申请单)
 * </pre>
 */
@Path("orgdrive")
@JaxrsDescribe("企业网盘")
public class OrgDriveAction extends StandardJaxrsAction {

	private static Logger logger = LoggerFactory.getLogger(OrgDriveAction.class);

	/** 企业盘物理持有者。与「聊聊转存」一致，使用 xadmin（虚拟管理员，无组织身份但可持有文件）。 */
	private static final String HOLDER_DEFAULT = "xadmin";

	/** 根目录名（Unicode 转义，避免编译期编码差异导致中文乱码）。 */
	private static final String ROOT_NAME = "\u4f01\u4e1a\u7f51\u76d8";

	private static final String TOP_FOLD = "$$TOP_FOLD";

	/** FileStatus 在库中存的是中文名，非枚举名。 */
	private static final String ST_VALID = "\u6b63\u5e38";

	private static final String ST_DELETED = "\u5df2\u5220\u9664";

	private static final String ST_PENDING = "pending";
	private static final String ST_APPROVED = "approved";
	private static final String ST_REJECTED = "rejected";
	private static final String ST_EXECUTED = "executed";

	/* ======================================================================
	 *  路由
	 * ====================================================================== */

	@GET
	@Path("drive")
	@Produces(HttpMediaType.APPLICATION_JSON_UTF_8)
	@Consumes(MediaType.APPLICATION_JSON)
	public void drive(@Suspended final AsyncResponse asyncResponse, @Context HttpServletRequest request) {
		ActionResult<WoDrive> result = new ActionResult<>();
		EffectivePerson effectivePerson = this.effectivePerson(request);
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			EntityManager em = emc.beginTransaction(Folder2.class);
			String holder = cfgGet(em, "holder", HOLDER_DEFAULT);
			String rootId = ensureRoot(em, holder, effectivePerson.getDistinguishedName());
			WoDrive wo = new WoDrive();
			wo.setRootId(rootId);
			wo.setRootName(ROOT_NAME);
			wo.setHolder(holder);
			wo.setMe(effectivePerson.getDistinguishedName());
			wo.setCanWrite(canWrite(em, effectivePerson.getDistinguishedName()));
			wo.setCanApprove(hasAnyApproveDuty(em, effectivePerson.getDistinguishedName()));
			em.getTransaction().commit();
			result.setData(wo);
		} catch (Exception e) {
			logger.error(e, effectivePerson, request, null);
			result.error(e);
		}
		asyncResponse.resume(ResponseFactory.getEntityTagActionResultResponse(request, result));
	}

	@GET
	@Path("list/{folderId}")
	@Produces(HttpMediaType.APPLICATION_JSON_UTF_8)
	@Consumes(MediaType.APPLICATION_JSON)
	public void list(@Suspended final AsyncResponse asyncResponse, @Context HttpServletRequest request,
			@PathParam("folderId") String folderId) {
		ActionResult<WoList> result = new ActionResult<>();
		EffectivePerson effectivePerson = this.effectivePerson(request);
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			EntityManager em = emc.beginTransaction(Folder2.class);
			String holder = cfgGet(em, "holder", HOLDER_DEFAULT);
			String rootId = ensureRoot(em, holder, effectivePerson.getDistinguishedName());
			String target = normalizeFolderId(folderId, rootId);
			if (!isInDrive(em, holder, rootId, target)) {
				throw new Exception("目标目录不在企业网盘内");
			}
			WoList wo = new WoList();
			wo.setId(target);
			wo.setRootId(rootId);
			wo.setName(target.equals(rootId) ? ROOT_NAME : folderName(em, holder, target));
			wo.setPath(pathOf(em, holder, rootId, target));
			wo.setFolders(listFolders(em, holder, rootId, target));
			wo.setFiles(listFiles(em, holder, target));
			em.getTransaction().commit();
			result.setData(wo);
		} catch (Exception e) {
			logger.error(e, effectivePerson, request, null);
			result.error(e);
		}
		asyncResponse.resume(ResponseFactory.getEntityTagActionResultResponse(request, result));
	}

	@POST
	@Path("folder")
	@Produces(HttpMediaType.APPLICATION_JSON_UTF_8)
	@Consumes(MediaType.APPLICATION_JSON)
	public void createFolder(@Suspended final AsyncResponse asyncResponse, @Context HttpServletRequest request,
			JsonElement jsonElement) {
		ActionResult<WoId> result = new ActionResult<>();
		EffectivePerson effectivePerson = this.effectivePerson(request);
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			EntityManager em = emc.beginTransaction(Folder2.class);
			String person = effectivePerson.getDistinguishedName();
			String holder = cfgGet(em, "holder", HOLDER_DEFAULT);
			String rootId = ensureRoot(em, holder, person);
			if (!canWrite(em, person)) {
				throw new Exception("你不在企业网盘写入名单内，无法新建目录");
			}
			JsonObject json = jsonElement.getAsJsonObject();
			String name = getStr(json, "name", "").trim();
			String superior = normalizeFolderId(getStr(json, "superior", rootId), rootId);
			if (StringUtils.isEmpty(name)) {
				throw new Exception("目录名称不能为空");
			}
			if (name.length() > 100) {
				throw new Exception("目录名称过长（上限 100 字）");
			}
			if (!isInDrive(em, holder, rootId, superior)) {
				throw new Exception("目标目录不在企业网盘内");
			}
			String finalName = uniqueFolderName(em, holder, superior, name);
			String id = UUID.randomUUID().toString();
			Query q = em.createNativeQuery("INSERT INTO FILE_FOLDER2 (xid,xcreateTime,xupdateTime,xlastUpdateTime,"
					+ "xname,xperson,xstatus,xsuperior,xsequence,xdistributeFactor) "
					+ "VALUES (?1,now(),now(),now(),?2,?3,?4,?5,null,0)");
			q.setParameter(1, id).setParameter(2, finalName).setParameter(3, holder)
					.setParameter(4, ST_VALID).setParameter(5, superior);
			q.executeUpdate();
			markDir(em, id, person);
			em.getTransaction().commit();
			WoId wo = new WoId();
			wo.setId(id);
			result.setData(wo);
		} catch (Exception e) {
			logger.error(e, effectivePerson, request, jsonElement);
			result.error(e);
		}
		asyncResponse.resume(ResponseFactory.getEntityTagActionResultResponse(request, result));
	}

	@POST
	@Path("consign")
	@Produces(HttpMediaType.APPLICATION_JSON_UTF_8)
	@Consumes(MediaType.APPLICATION_JSON)
	public void consign(@Suspended final AsyncResponse asyncResponse, @Context HttpServletRequest request,
			JsonElement jsonElement) {
		ActionResult<WoConsign> result = new ActionResult<>();
		EffectivePerson effectivePerson = this.effectivePerson(request);
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			EntityManager em = emc.beginTransaction(Folder2.class);
			String person = effectivePerson.getDistinguishedName();
			String holder = cfgGet(em, "holder", HOLDER_DEFAULT);
			String rootId = ensureRoot(em, holder, person);
			if (!canWrite(em, person)) {
				throw new Exception("你不在企业网盘写入名单内，无法投放");
			}
			JsonObject json = jsonElement.getAsJsonObject();
			String kind = getStr(json, "kind", "attachment");
			String sourceId = getStr(json, "id", "");
			String target = normalizeFolderId(getStr(json, "target", rootId), rootId);
			if (StringUtils.isEmpty(sourceId)) {
				throw new Exception("缺少投放源标识");
			}
			if (!isInDrive(em, holder, rootId, target)) {
				throw new Exception("目标目录不在企业网盘内");
			}
			int files = 0, dirs = 0;
			String newId;
			if ("folder".equals(kind)) {
				// 源目录必须属于调用者本人
				List<?> src = em.createNativeQuery("SELECT xname FROM FILE_FOLDER2 WHERE xid=?1 "
						+ "AND (xperson=?2 OR (LOCATE('@',xperson)=0 AND xperson=?3)) AND xstatus=?4")
						.setParameter(1, sourceId).setParameter(2, person).setParameter(3, bareName(person))
						.setParameter(4, ST_VALID).getResultList();
				if (src.isEmpty()) {
					throw new Exception("源目录不存在或不属于你");
				}
				String name = uniqueFolderName(em, holder, target, String.valueOf(src.get(0)));
				newId = UUID.randomUUID().toString();
				em.createNativeQuery("INSERT INTO FILE_FOLDER2 (xid,xcreateTime,xupdateTime,xlastUpdateTime,"
						+ "xname,xperson,xstatus,xsuperior,xsequence,xdistributeFactor) "
						+ "VALUES (?1,now(),now(),now(),?2,?3,?4,?5,null,0)")
						.setParameter(1, newId).setParameter(2, name).setParameter(3, holder)
						.setParameter(4, ST_VALID).setParameter(5, target).executeUpdate();
				markDir(em, newId, person);
				int[] acc = copyFolderDeep(em, sourceId, newId, holder, person);
				files = acc[0];
				dirs = acc[1];
			} else {
				newId = copyAttachment(em, sourceId, target, holder, person, true);
				files = 1;
			}
			em.getTransaction().commit();
			WoConsign wo = new WoConsign();
			wo.setId(newId);
			wo.setCopiedFiles(files);
			wo.setCopiedFolders(dirs);
			result.setData(wo);
		} catch (Exception e) {
			logger.error(e, effectivePerson, request, jsonElement);
			result.error(e);
		}
		asyncResponse.resume(ResponseFactory.getEntityTagActionResultResponse(request, result));
	}

	@POST
	@Path("delete")
	@Produces(HttpMediaType.APPLICATION_JSON_UTF_8)
	@Consumes(MediaType.APPLICATION_JSON)
	public void deleteRequest(@Suspended final AsyncResponse asyncResponse, @Context HttpServletRequest request,
			JsonElement jsonElement) {
		ActionResult<WoRequest> result = new ActionResult<>();
		EffectivePerson effectivePerson = this.effectivePerson(request);
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			EntityManager em = emc.beginTransaction(Folder2.class);
			String person = effectivePerson.getDistinguishedName();
			String holder = cfgGet(em, "holder", HOLDER_DEFAULT);
			String rootId = ensureRoot(em, holder, person);
			JsonObject json = jsonElement.getAsJsonObject();
			String kind = getStr(json, "kind", "attachment");
			String targetId = getStr(json, "id", "");
			String reason = getStr(json, "reason", "").trim();
			if (StringUtils.isEmpty(targetId)) {
				throw new Exception("缺少删除目标标识");
			}
			if (targetId.equals(rootId)) {
				throw new Exception("企业网盘根目录不允许删除");
			}
			String name;
			String parent;
			if ("folder".equals(kind)) {
				List<?> rows = em.createNativeQuery("SELECT xname,xsuperior FROM FILE_FOLDER2 WHERE xid=?1 AND xperson=?2 AND xstatus=?3")
						.setParameter(1, targetId).setParameter(2, holder).setParameter(3, ST_VALID).getResultList();
				if (rows.isEmpty()) {
					throw new Exception("目标目录不存在");
				}
				Object[] r = (Object[]) rows.get(0);
				name = String.valueOf(r[0]);
				parent = String.valueOf(r[1]);
			} else {
				List<?> rows = em.createNativeQuery("SELECT xname,xfolder FROM FILE_ATTACHMENT2 WHERE xid=?1 AND xperson=?2 AND xstatus=?3")
						.setParameter(1, targetId).setParameter(2, holder).setParameter(3, ST_VALID).getResultList();
				if (rows.isEmpty()) {
					throw new Exception("目标文件不存在");
				}
				Object[] r = (Object[]) rows.get(0);
				name = String.valueOf(r[0]);
				parent = String.valueOf(r[1]);
			}
			if (!isInDrive(em, holder, rootId, parent)) {
				throw new Exception("目标不在企业网盘内");
			}
			// 同一目标已有待审单 → 拒绝重复提交
			List<?> dup = em.createNativeQuery("SELECT xid FROM O2_ORGDRIVE_DEL_REQ WHERE xtargetId=?1 AND xstatus=?2")
					.setParameter(1, targetId).setParameter(2, ST_PENDING).getResultList();
			if (!dup.isEmpty()) {
				throw new Exception("该目标已有待审批的删除申请，请勿重复提交");
			}
			String creator = dirCreator(em, parent);
			String approver = resolveApprover(em, creator, person);
			if (StringUtils.isEmpty(approver)) {
				throw new Exception("该目录未配置审批人，且你不能审批自己创建的目录的删除申请；"
						+ "请管理员在「删除审核」设置中配置兜底审批人");
			}
			String id = UUID.randomUUID().toString();
			em.createNativeQuery("INSERT INTO O2_ORGDRIVE_DEL_REQ (xid,xtargetKind,xtargetId,xtargetName,xtargetPath,"
					+ "xapplicant,xreason,xstatus,xapprover,xapproveTime,xnote,xcreateTime) "
					+ "VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,null,null,now())")
					.setParameter(1, id).setParameter(2, kind).setParameter(3, targetId).setParameter(4, name)
					.setParameter(5, pathString(em, holder, rootId, parent) + "/" + name)
					.setParameter(6, person).setParameter(7, reason).setParameter(8, ST_PENDING)
					.setParameter(9, approver).executeUpdate();
			em.getTransaction().commit();
			WoRequest wo = new WoRequest();
			wo.setId(id);
			wo.setTargetKind(kind);
			wo.setTargetId(targetId);
			wo.setTargetName(name);
			wo.setApplicant(person);
			wo.setReason(reason);
			wo.setStatus(ST_PENDING);
			wo.setApprover(approver);
			result.setData(wo);
		} catch (Exception e) {
			logger.error(e, effectivePerson, request, jsonElement);
			result.error(e);
		}
		asyncResponse.resume(ResponseFactory.getEntityTagActionResultResponse(request, result));
	}

	@GET
	@Path("requests/{status}")
	@Produces(HttpMediaType.APPLICATION_JSON_UTF_8)
	@Consumes(MediaType.APPLICATION_JSON)
	public void requests(@Suspended final AsyncResponse asyncResponse, @Context HttpServletRequest request,
			@PathParam("status") String status) {
		ActionResult<List<WoRequest>> result = new ActionResult<>();
		EffectivePerson effectivePerson = this.effectivePerson(request);
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			EntityManager em = emc.beginTransaction(Folder2.class);
			String person = effectivePerson.getDistinguishedName();
			String st = StringUtils.isEmpty(status) || "all".equals(status) ? null : status;
			/* ★ 原生查询只支持位置参数（?1/?2…），命名参数会抛
			   IllegalArgumentException: named parameter is not allowed in native SQL query */
			boolean duty = hasAnyApproveDuty(em, person);
			StringBuilder sb = new StringBuilder("SELECT xid,xtargetKind,xtargetId,xtargetName,xtargetPath,"
					+ "xapplicant,xreason,xstatus,xapprover,xapproveTime,xnote,xcreateTime FROM O2_ORGDRIVE_DEL_REQ WHERE 1=1");
			int pIdx = 1;
			Integer stIdx = null, meIdx = null;
			if (st != null) {
				stIdx = pIdx++;
				sb.append(" AND xstatus=?").append(stIdx);
			}
			// 非审批人只能看到自己提交的申请
			if (!duty) {
				meIdx = pIdx++;
				sb.append(" AND xapplicant=?").append(meIdx);
			}
			sb.append(" ORDER BY xcreateTime DESC LIMIT 300");
			Query q = em.createNativeQuery(sb.toString());
			if (stIdx != null) {
				q.setParameter(stIdx, st);
			}
			if (meIdx != null) {
				q.setParameter(meIdx, person);
			}
			List<WoRequest> wos = new ArrayList<>();
			for (Object o : q.getResultList()) {
				Object[] r = (Object[]) o;
				WoRequest wo = new WoRequest();
				wo.setId(str(r[0]));
				wo.setTargetKind(str(r[1]));
				wo.setTargetId(str(r[2]));
				wo.setTargetName(str(r[3]));
				wo.setTargetPath(str(r[4]));
				wo.setApplicant(str(r[5]));
				wo.setReason(str(r[6]));
				wo.setStatus(str(r[7]));
				wo.setApprover(str(r[8]));
				wo.setApproveTime(str(r[9]));
				wo.setNote(str(r[10]));
				wo.setCreateTime(str(r[11]));
				wo.setMine(person.equals(wo.getApplicant()));
				wo.setCanApprove(person.equals(wo.getApprover()) && ST_PENDING.equals(wo.getStatus()));
				wos.add(wo);
			}
			result.setData(wos);
		} catch (Exception e) {
			logger.error(e, effectivePerson, request, null);
			result.error(e);
		}
		asyncResponse.resume(ResponseFactory.getEntityTagActionResultResponse(request, result));
	}

	@POST
	@Path("approve")
	@Produces(HttpMediaType.APPLICATION_JSON_UTF_8)
	@Consumes(MediaType.APPLICATION_JSON)
	public void approve(@Suspended final AsyncResponse asyncResponse, @Context HttpServletRequest request,
			JsonElement jsonElement) {
		ActionResult<WoApprove> result = new ActionResult<>();
		EffectivePerson effectivePerson = this.effectivePerson(request);
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			EntityManager em = emc.beginTransaction(Folder2.class);
			String person = effectivePerson.getDistinguishedName();
			String holder = cfgGet(em, "holder", HOLDER_DEFAULT);
			String rootId = ensureRoot(em, holder, person);
			JsonObject json = jsonElement.getAsJsonObject();
			String requestId = getStr(json, "requestId", "");
			String action = getStr(json, "action", "approve");
			String note = getStr(json, "note", "").trim();
			if (StringUtils.isEmpty(requestId)) {
				throw new Exception("缺少申请单标识");
			}
			List<?> rows = em.createNativeQuery("SELECT xtargetKind,xtargetId,xapplicant,xstatus,xapprover,xtargetName "
					+ "FROM O2_ORGDRIVE_DEL_REQ WHERE xid=?1")
					.setParameter(1, requestId).getResultList();
			if (rows.isEmpty()) {
				throw new Exception("申请单不存在");
			}
			Object[] r = (Object[]) rows.get(0);
			String kind = str(r[0]), targetId = str(r[1]), applicant = str(r[2]);
			String curStatus = str(r[3]), approver = str(r[4]), name = str(r[5]);
			if (!ST_PENDING.equals(curStatus)) {
				throw new Exception("该申请已处理（当前状态：" + curStatus + "）");
			}
			if (!person.equals(approver) && !isFallbackApprover(em, person)) {
				throw new Exception("你无权审批该申请");
			}
			if (person.equals(applicant)) {
				throw new Exception("申请人不得审批自己提交的删除申请");
			}
			WoApprove wo = new WoApprove();
			if ("reject".equals(action)) {
				em.createNativeQuery("UPDATE O2_ORGDRIVE_DEL_REQ SET xstatus=?1,xapprover=?2,xapproveTime=now(),xnote=?3 WHERE xid=?4")
						.setParameter(1, ST_REJECTED).setParameter(2, person).setParameter(3, note)
						.setParameter(4, requestId).executeUpdate();
				em.getTransaction().commit();
				wo.setExecuted(false);
				wo.setStatus(ST_REJECTED);
				result.setData(wo);
			} else {
				// 执行删除前重校验：目标仍在企业盘内且状态正常
				boolean removed;
				if ("folder".equals(kind)) {
					List<?> chk = em.createNativeQuery("SELECT xsuperior FROM FILE_FOLDER2 WHERE xid=?1 AND xperson=?2 AND xstatus=?3")
							.setParameter(1, targetId).setParameter(2, holder).setParameter(3, ST_VALID).getResultList();
					if (chk.isEmpty()) {
						em.createNativeQuery("UPDATE O2_ORGDRIVE_DEL_REQ SET xstatus='stale',xapprover=?1,"
								+ "xapproveTime=now(),xnote=CONCAT(IFNULL(xnote,''),' [目标已不存在]') WHERE xid=?2")
								.setParameter(1, person).setParameter(2, requestId).executeUpdate();
						em.getTransaction().commit();
						throw new Exception("目标已不存在，申请单标记为 stale");
					}
					String parent = String.valueOf(chk.get(0));
					if (!isInDrive(em, holder, rootId, parent)) {
						throw new Exception("目标已不在企业网盘内，拒绝执行");
					}
					removeFolderDeep(em, holder, targetId);
					removed = true;
				} else {
					int n = em.createNativeQuery("DELETE FROM FILE_ATTACHMENT2 WHERE xid=?1 AND xperson=?2")
							.setParameter(1, targetId).setParameter(2, holder).executeUpdate();
					removed = n > 0;
				}
				em.createNativeQuery("UPDATE O2_ORGDRIVE_DEL_REQ SET xstatus=?1,xapprover=?2,xapproveTime=now(),xnote=?3 WHERE xid=?4")
						.setParameter(1, ST_EXECUTED).setParameter(2, person).setParameter(3, note)
						.setParameter(4, requestId).executeUpdate();
				em.getTransaction().commit();
				wo.setExecuted(removed);
				wo.setStatus(ST_EXECUTED);
				wo.setTargetName(name);
				result.setData(wo);
			}
		} catch (Exception e) {
			logger.error(e, effectivePerson, request, jsonElement);
			result.error(e);
		}
		asyncResponse.resume(ResponseFactory.getEntityTagActionResultResponse(request, result));
	}

	@GET
	@Path("file/{fileId}/download")
	@Consumes(MediaType.APPLICATION_JSON)
	public void download(@Suspended final AsyncResponse asyncResponse, @Context HttpServletRequest request,
			@PathParam("fileId") String fileId) {
		ActionResult<WoDownload> result = new ActionResult<>();
		EffectivePerson effectivePerson = this.effectivePerson(request);
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			EntityManager em = emc.beginTransaction(Folder2.class);
			String holder = cfgGet(em, "holder", HOLDER_DEFAULT);
			String rootId = ensureRoot(em, holder, effectivePerson.getDistinguishedName());
			Attachment2 att = emc.find(fileId, Attachment2.class);
			if (att == null || !holder.equals(att.getPerson())) {
				throw new Exception("企业网盘文件不存在");
			}
			if (!isInDrive(em, holder, rootId, att.getFolder())) {
				throw new Exception("文件不在企业网盘内");
			}
			OriginFile originFile = emc.find(att.getOriginFile(), OriginFile.class);
			if (originFile == null) {
				throw new Exception("文件内容不存在");
			}
			StorageMapping mapping = ThisApplication.context().storageMappings().get(OriginFile.class,
					originFile.getStorage());
			if (mapping == null) {
				throw new Exception("存储映射不存在：" + originFile.getStorage());
			}
			final String name = att.getName();
			StreamingOutput streamingOutput = output -> {
				try {
					originFile.readContent(mapping, output);
					output.flush();
				} catch (Exception e) {
					logger.warn("{} 企业网盘文件下载异常：{}", name, e.getMessage());
				}
			};
			String etag = att.getId() + (att.getUpdateTime() == null ? "" : att.getUpdateTime().getTime());
			result.setData(new WoDownload(streamingOutput, this.contentType(false, name),
					this.contentDisposition(false, name), originFile.getLength(), etag));
		} catch (Exception e) {
			logger.error(e, effectivePerson, request, null);
			result.error(e);
		}
		asyncResponse.resume(ResponseFactory.getEntityTagActionResultResponse(request, result));
	}

	public static class WoDownload extends com.x.base.core.project.jaxrs.WoFile {
		private static final long serialVersionUID = 1L;

		public WoDownload(StreamingOutput streamingOutput, String contentType, String contentDisposition,
				Long contentLength, String fastETag) {
			super(streamingOutput, contentType, contentDisposition, contentLength, fastETag);
		}
	}

	@GET
	@Path("config")
	@Produces(HttpMediaType.APPLICATION_JSON_UTF_8)
	@Consumes(MediaType.APPLICATION_JSON)
	public void getConfig(@Suspended final AsyncResponse asyncResponse, @Context HttpServletRequest request) {
		ActionResult<WoConfig> result = new ActionResult<>();
		EffectivePerson effectivePerson = this.effectivePerson(request);
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			EntityManager em = emc.beginTransaction(Folder2.class);
			WoConfig wo = new WoConfig();
			wo.setHolder(cfgGet(em, "holder", HOLDER_DEFAULT));
			wo.setWriterPersonList(cfgList(em, "writerPersonList"));
			wo.setFallbackApproverPersonList(cfgList(em, "fallbackApproverPersonList"));
			wo.setCanEdit(personCanEditConfig(em, effectivePerson.getDistinguishedName()));
			result.setData(wo);
		} catch (Exception e) {
			logger.error(e, effectivePerson, request, null);
			result.error(e);
		}
		asyncResponse.resume(ResponseFactory.getEntityTagActionResultResponse(request, result));
	}

	@POST
	@Path("config")
	@Produces(HttpMediaType.APPLICATION_JSON_UTF_8)
	@Consumes(MediaType.APPLICATION_JSON)
	public void saveConfig(@Suspended final AsyncResponse asyncResponse, @Context HttpServletRequest request,
			JsonElement jsonElement) {
		ActionResult<WoConfig> result = new ActionResult<>();
		EffectivePerson effectivePerson = this.effectivePerson(request);
		try (EntityManagerContainer emc = EntityManagerContainerFactory.instance().create()) {
			EntityManager em = emc.beginTransaction(Folder2.class);
			String person = effectivePerson.getDistinguishedName();
			if (!personCanEditConfig(em, person)) {
				throw new Exception("你无权修改企业网盘设置");
			}
			JsonObject json = jsonElement.getAsJsonObject();
			if (json.has("writerPersonList")) {
				cfgSet(em, "writerPersonList", joinList(json.getAsJsonArray("writerPersonList")));
			}
			if (json.has("fallbackApproverPersonList")) {
				cfgSet(em, "fallbackApproverPersonList", joinList(json.getAsJsonArray("fallbackApproverPersonList")));
			}
			em.getTransaction().commit();
			WoConfig wo = new WoConfig();
			wo.setHolder(cfgGet(em, "holder", HOLDER_DEFAULT));
			wo.setWriterPersonList(cfgList(em, "writerPersonList"));
			wo.setFallbackApproverPersonList(cfgList(em, "fallbackApproverPersonList"));
			wo.setCanEdit(true);
			result.setData(wo);
		} catch (Exception e) {
			logger.error(e, effectivePerson, request, jsonElement);
			result.error(e);
		}
		asyncResponse.resume(ResponseFactory.getEntityTagActionResultResponse(request, result));
	}

	/* ======================================================================
	 *  根目录 / 祖先链
	 * ====================================================================== */

	/** 定位企业盘根，不存在则创建（首次调用自举）。 */
	private String ensureRoot(EntityManager em, String holder, String creator) {
		List<?> rows = em.createNativeQuery("SELECT xid FROM FILE_FOLDER2 WHERE xperson=?1 AND xsuperior=?2 AND xname=?3")
				.setParameter(1, holder).setParameter(2, TOP_FOLD).setParameter(3, ROOT_NAME).getResultList();
		if (!rows.isEmpty()) {
			return str(rows.get(0));
		}
		String id = UUID.randomUUID().toString();
		em.createNativeQuery("INSERT INTO FILE_FOLDER2 (xid,xcreateTime,xupdateTime,xlastUpdateTime,"
				+ "xname,xperson,xstatus,xsuperior,xsequence,xdistributeFactor) "
				+ "VALUES (?1,now(),now(),now(),?2,?3,?4,?5,null,0)")
				.setParameter(1, id).setParameter(2, ROOT_NAME).setParameter(3, holder)
				.setParameter(4, ST_VALID).setParameter(5, TOP_FOLD).executeUpdate();
		markDir(em, id, creator);
		return id;
	}

	private String normalizeFolderId(String folderId, String rootId) {
		if (StringUtils.isEmpty(folderId) || TOP_FOLD.equals(folderId) || "root".equals(folderId)) {
			return rootId;
		}
		return folderId;
	}

	/** 目标目录是否位于企业盘根之内（含根本身），防越界操作。 */
	private boolean isInDrive(EntityManager em, String holder, String rootId, String folderId) {
		if (StringUtils.isEmpty(folderId)) {
			return false;
		}
		String cur = folderId;
		for (int i = 0; i < 64; i++) {
			if (cur.equals(rootId)) {
				return true;
			}
			List<?> rows = em.createNativeQuery("SELECT xsuperior FROM FILE_FOLDER2 WHERE xid=?1 AND xperson=?2")
					.setParameter(1, cur).setParameter(2, holder).getResultList();
			if (rows.isEmpty()) {
				return false;
			}
			cur = str(rows.get(0));
			if (TOP_FOLD.equals(cur)) {
				return false;
			}
		}
		return false;
	}

	private String folderName(EntityManager em, String holder, String folderId) {
		List<?> rows = em.createNativeQuery("SELECT xname FROM FILE_FOLDER2 WHERE xid=?1 AND xperson=?2")
				.setParameter(1, folderId).setParameter(2, holder).getResultList();
		return rows.isEmpty() ? "" : str(rows.get(0));
	}

	private List<WoPath> pathOf(EntityManager em, String holder, String rootId, String folderId) {
		List<WoPath> list = new ArrayList<>();
		String cur = folderId;
		for (int i = 0; i < 64 && !StringUtils.isEmpty(cur); i++) {
			List<?> rows = em.createNativeQuery("SELECT xname,xsuperior FROM FILE_FOLDER2 WHERE xid=?1 AND xperson=?2")
					.setParameter(1, cur).setParameter(2, holder).getResultList();
			if (rows.isEmpty()) {
				break;
			}
			Object[] r = (Object[]) rows.get(0);
			WoPath p = new WoPath();
			p.setId(cur);
			p.setName(str(r[0]));
			list.add(0, p);
			if (cur.equals(rootId)) {
				break;
			}
			cur = str(r[1]);
		}
		return list;
	}

	private String pathString(EntityManager em, String holder, String rootId, String folderId) {
		StringBuilder sb = new StringBuilder();
		for (WoPath p : pathOf(em, holder, rootId, folderId)) {
			sb.append("/").append(p.getName());
		}
		return sb.length() == 0 ? "/" : sb.toString();
	}

	/* ======================================================================
	 *  列表 / 复制 / 删除
	 * ====================================================================== */

	private List<WoFolder> listFolders(EntityManager em, String holder, String rootId, String parent) {
		List<WoFolder> list = new ArrayList<>();
		List<?> rows = em.createNativeQuery("SELECT xid,xname,xlastUpdateTime FROM FILE_FOLDER2 "
				+ "WHERE xperson=?1 AND xsuperior=?2 AND xstatus=?3 ORDER BY xname")
				.setParameter(1, holder).setParameter(2, parent).setParameter(3, ST_VALID).getResultList();
		for (Object o : rows) {
			Object[] r = (Object[]) o;
			WoFolder f = new WoFolder();
			f.setId(str(r[0]));
			f.setName(str(r[1]));
			f.setUpdateTime(str(r[2]));
			f.setCreator(dirCreator(em, str(r[0])));
			list.add(f);
		}
		return list;
	}

	private List<WoFile> listFiles(EntityManager em, String holder, String parent) {
		List<WoFile> list = new ArrayList<>();
		List<?> rows = em.createNativeQuery("SELECT xid,xname,xextension,xlength,xlastUpdateTime,xoriginFile "
				+ "FROM FILE_ATTACHMENT2 WHERE xperson=?1 AND xfolder=?2 AND xstatus=?3 ORDER BY xname")
				.setParameter(1, holder).setParameter(2, parent).setParameter(3, ST_VALID).getResultList();
		for (Object o : rows) {
			Object[] r = (Object[]) o;
			WoFile f = new WoFile();
			f.setId(str(r[0]));
			f.setName(str(r[1]));
			f.setExtension(str(r[2]));
			f.setLength(r[3] == null ? 0L : Long.parseLong(String.valueOf(r[3])));
			f.setUpdateTime(str(r[4]));
			list.add(f);
		}
		return list;
	}

	/**
	 * 复制单个文件进企业盘（零字节拷贝：复用源 OriginFile，仅新增元数据行）。
	 * 源必须属于 {@code owner}。
	 */
	private String copyAttachment(EntityManager em, String sourceId, String target, String holder, String owner,
			boolean requireOwner) {
		String sql = requireOwner
				? "SELECT xname,xextension,xlength,xoriginFile,xtype FROM FILE_ATTACHMENT2 WHERE xid=?1 "
						+ "AND (xperson=?2 OR (LOCATE('@',xperson)=0 AND xperson=?3)) AND xstatus=?4"
				: "SELECT xname,xextension,xlength,xoriginFile,xtype FROM FILE_ATTACHMENT2 WHERE xid=?1 AND xstatus=?2";
		Query q = em.createNativeQuery(sql);
		if (requireOwner) {
			q.setParameter(1, sourceId).setParameter(2, owner).setParameter(3, bareName(owner))
					.setParameter(4, ST_VALID);
		} else {
			q.setParameter(1, sourceId).setParameter(2, ST_VALID);
		}
		List<?> rows = q.getResultList();
		if (rows.isEmpty()) {
			throw new RuntimeException("源文件不存在或无权访问");
		}
		Object[] r = (Object[]) rows.get(0);
		String name = uniqueFileName(em, holder, target, str(r[0]));
		String id = UUID.randomUUID().toString();
		em.createNativeQuery("INSERT INTO FILE_ATTACHMENT2 (xid,xcreateTime,xupdateTime,xlastUpdateTime,"
				+ "xname,xextension,xlength,xoriginFile,xtype,xperson,xfolder,xstatus,xlastUpdatePerson,xfileVersion,"
				+ "xdescription,xsequence,xdistributeFactor) "
				+ "VALUES (?1,now(),now(),now(),?2,?3,?4,?5,?6,?7,?8,?9,?10,null,null,null,0)")
				.setParameter(1, id).setParameter(2, name).setParameter(3, str(r[1]))
				.setParameter(4, r[2] == null ? 0L : Long.parseLong(String.valueOf(r[2])))
				.setParameter(5, str(r[3])).setParameter(6, str(r[4]))
				.setParameter(7, holder).setParameter(8, target).setParameter(9, ST_VALID)
				.setParameter(10, owner).executeUpdate();
		return id;
	}

	/** 递归复制目录（含子目录与文件），返回 {文件数, 目录数}。 */
	private int[] copyFolderDeep(EntityManager em, String sourceFolder, String newFolder, String holder, String owner) {
		int files = 0, dirs = 0;
		List<?> atts = em.createNativeQuery("SELECT xid FROM FILE_ATTACHMENT2 WHERE "
				+ "(xperson=?1 OR (LOCATE('@',xperson)=0 AND xperson=?2)) AND xfolder=?3 AND xstatus=?4")
				.setParameter(1, owner).setParameter(2, bareName(owner)).setParameter(3, sourceFolder)
				.setParameter(4, ST_VALID).getResultList();
		for (Object o : atts) {
			copyAttachment(em, str(o), newFolder, holder, owner, true);
			files++;
		}
		List<?> subs = em.createNativeQuery("SELECT xid,xname FROM FILE_FOLDER2 WHERE "
				+ "(xperson=?1 OR (LOCATE('@',xperson)=0 AND xperson=?2)) AND xsuperior=?3 AND xstatus=?4")
				.setParameter(1, owner).setParameter(2, bareName(owner)).setParameter(3, sourceFolder)
				.setParameter(4, ST_VALID).getResultList();
		for (Object o : subs) {
			Object[] r = (Object[]) o;
			String subId = UUID.randomUUID().toString();
			String subName = uniqueFolderName(em, holder, newFolder, str(r[1]));
			em.createNativeQuery("INSERT INTO FILE_FOLDER2 (xid,xcreateTime,xupdateTime,xlastUpdateTime,"
					+ "xname,xperson,xstatus,xsuperior,xsequence,xdistributeFactor) "
					+ "VALUES (?1,now(),now(),now(),?2,?3,?4,?5,null,0)")
					.setParameter(1, subId).setParameter(2, subName).setParameter(3, holder)
					.setParameter(4, ST_VALID).setParameter(5, newFolder).executeUpdate();
			markDir(em, subId, owner);
			int[] acc = copyFolderDeep(em, str(r[0]), subId, holder, owner);
			files += acc[0];
			dirs += acc[1] + 1;
		}
		return new int[] { files, dirs };
	}

	private void removeFolderDeep(EntityManager em, String holder, String folderId) {
		List<?> atts = em.createNativeQuery("SELECT xid FROM FILE_ATTACHMENT2 WHERE xperson=?1 AND xfolder=?2")
				.setParameter(1, holder).setParameter(2, folderId).getResultList();
		for (Object o : atts) {
			em.createNativeQuery("DELETE FROM FILE_ATTACHMENT2 WHERE xid=?1").setParameter(1, str(o)).executeUpdate();
		}
		List<?> subs = em.createNativeQuery("SELECT xid FROM FILE_FOLDER2 WHERE xperson=?1 AND xsuperior=?2")
				.setParameter(1, holder).setParameter(2, folderId).getResultList();
		for (Object o : subs) {
			removeFolderDeep(em, holder, str(o));
		}
		em.createNativeQuery("DELETE FROM FILE_FOLDER2 WHERE xid=?1").setParameter(1, folderId).executeUpdate();
		em.createNativeQuery("DELETE FROM O2_ORGDRIVE_DIR WHERE xfolderId=?1").setParameter(1, folderId).executeUpdate();
	}

	/* ======================================================================
	 *  命名去重（不覆盖，追加 " (n)"）
	 * ====================================================================== */

	private String uniqueFolderName(EntityManager em, String holder, String parent, String name) {
		String candidate = name;
		for (int i = 2; i < 100; i++) {
			List<?> rows = em.createNativeQuery("SELECT xid FROM FILE_FOLDER2 WHERE xperson=?1 AND xsuperior=?2 AND xname=?3 AND xstatus=?4")
					.setParameter(1, holder).setParameter(2, parent).setParameter(3, candidate)
					.setParameter(4, ST_VALID).getResultList();
			if (rows.isEmpty()) {
				return candidate;
			}
			candidate = name + " (" + i + ")";
		}
		return name + " (" + System.currentTimeMillis() + ")";
	}

	private String uniqueFileName(EntityManager em, String holder, String parent, String name) {
		String base = name;
		String ext = "";
		int dot = name.lastIndexOf('.');
		if (dot > 0) {
			base = name.substring(0, dot);
			ext = name.substring(dot);
		}
		String candidate = name;
		for (int i = 2; i < 100; i++) {
			List<?> rows = em.createNativeQuery("SELECT xid FROM FILE_ATTACHMENT2 WHERE xperson=?1 AND xfolder=?2 AND xname=?3 AND xstatus=?4")
					.setParameter(1, holder).setParameter(2, parent).setParameter(3, candidate)
					.setParameter(4, ST_VALID).getResultList();
			if (rows.isEmpty()) {
				return candidate;
			}
			candidate = base + " (" + i + ")" + ext;
		}
		return base + " (" + System.currentTimeMillis() + ")" + ext;
	}

	/* ======================================================================
	 *  目录元数据（逻辑创建者）与配置
	 * ====================================================================== */

	private void markDir(EntityManager em, String folderId, String creator) {
		em.createNativeQuery("INSERT INTO O2_ORGDRIVE_DIR (xfolderId,xcreator,xcreateTime) VALUES (?1,?2,now()) "
				+ "ON DUPLICATE KEY UPDATE xcreator=VALUES(xcreator)")
				.setParameter(1, folderId).setParameter(2, creator).executeUpdate();
	}

	/** 目录的逻辑创建者；未登记（如存量目录）时返回空串。 */
	private String dirCreator(EntityManager em, String folderId) {
		try {
			List<?> rows = em.createNativeQuery("SELECT xcreator FROM O2_ORGDRIVE_DIR WHERE xfolderId=?1")
					.setParameter(1, folderId).getResultList();
			return rows.isEmpty() ? "" : str(rows.get(0));
		} catch (Exception e) {
			return "";
		}
	}

	private String resolveApprover(EntityManager em, String creator, String applicant) {
		if (!StringUtils.isEmpty(creator) && !creator.equals(applicant)) {
			return creator;
		}
		List<String> fallback = cfgList(em, "fallbackApproverPersonList");
		for (String p : fallback) {
			if (!p.equals(applicant)) {
				return p;
			}
		}
		return "";
	}

	private boolean isFallbackApprover(EntityManager em, String person) {
		return cfgList(em, "fallbackApproverPersonList").contains(person);
	}

	private boolean hasAnyApproveDuty(EntityManager em, String person) {
		try {
			List<?> rows = em.createNativeQuery("SELECT COUNT(*) FROM O2_ORGDRIVE_DEL_REQ WHERE xapprover=?1 AND xstatus=?2")
					.setParameter(1, person).setParameter(2, ST_PENDING).getResultList();
			if (!rows.isEmpty() && Long.parseLong(String.valueOf(rows.get(0))) > 0) {
				return true;
			}
		} catch (Exception ignore) {
			// 表尚未创建时不影响只读视图
		}
		return isFallbackApprover(em, person);
	}

	/** 写入名单为空 = 全员可写（与现有「共享区可创建名单」同语义）。 */
	private boolean canWrite(EntityManager em, String person) {
		List<String> wl = cfgList(em, "writerPersonList");
		return wl.isEmpty() || wl.contains(person);
	}

	/**
	 * 谁能改企业盘设置：兜底审批人名单内的人。
	 * 未配置时仅允许「第一个触发初始化的人」之外的管理场景——为避免硬编码管理员，
	 * 此处回退为 false，由部署脚本初始化 fallbackApproverPersonList。
	 */
	private boolean personCanEditConfig(EntityManager em, String person) {
		return isFallbackApprover(em, person);
	}

	private String cfgGet(EntityManager em, String key, String def) {
		try {
			List<?> rows = em.createNativeQuery("SELECT xvalue FROM O2_ORGDRIVE_CFG WHERE xkey=?1")
					.setParameter(1, key).getResultList();
			return rows.isEmpty() ? def : str(rows.get(0));
		} catch (Exception e) {
			return def;
		}
	}

	private List<String> cfgList(EntityManager em, String key) {
		List<String> list = new ArrayList<>();
		String v = cfgGet(em, key, "");
		if (StringUtils.isEmpty(v)) {
			return list;
		}
		for (String s : v.split("\n")) {
			if (!StringUtils.isBlank(s)) {
				list.add(s.trim());
			}
		}
		return list;
	}

	private void cfgSet(EntityManager em, String key, String value) {
		em.createNativeQuery("INSERT INTO O2_ORGDRIVE_CFG (xkey,xvalue) VALUES (?1,?2) "
				+ "ON DUPLICATE KEY UPDATE xvalue=VALUES(xvalue)")
				.setParameter(1, key).setParameter(2, value == null ? "" : value).executeUpdate();
	}

	private String joinList(JsonArray arr) {
		StringBuilder sb = new StringBuilder();
		if (arr != null) {
			for (JsonElement e : arr) {
				String s = e == null || e.isJsonNull() ? "" : e.getAsString().trim();
				if (!StringUtils.isEmpty(s)) {
					if (sb.length() > 0) {
						sb.append("\n");
					}
					sb.append(s);
				}
			}
		}
		return sb.toString();
	}

	/* ======================================================================
	 *  杂项
	 * ====================================================================== */

	/** 人员 DN 的裸名（xadmin 代持的历史数据以裸名存 xperson）。 */
	private static String bareName(String person) {
		if (person == null) {
			return "";
		}
		int i = person.indexOf('@');
		return i > 0 ? person.substring(0, i) : person;
	}

	private static String str(Object o) {
		return o == null ? "" : String.valueOf(o);
	}

	private static String getStr(JsonObject json, String key, String def) {
		if (json == null || !json.has(key) || json.get(key).isJsonNull()) {
			return def;
		}
		try {
			return json.get(key).getAsString();
		} catch (Exception e) {
			return def;
		}
	}

	/* ======================================================================
	 *  Wo
	 * ====================================================================== */

	public static class WoDrive extends com.x.base.core.project.jaxrs.WrapBoolean {
		private static final long serialVersionUID = 1L;
		private String rootId;
		private String rootName;
		private String holder;
		private String me;
		private Boolean canWrite;
		private Boolean canApprove;

		public String getRootId() {
			return rootId;
		}

		public void setRootId(String rootId) {
			this.rootId = rootId;
		}

		public String getRootName() {
			return rootName;
		}

		public void setRootName(String rootName) {
			this.rootName = rootName;
		}

		public String getHolder() {
			return holder;
		}

		public void setHolder(String holder) {
			this.holder = holder;
		}

		public String getMe() {
			return me;
		}

		public void setMe(String me) {
			this.me = me;
		}

		public Boolean getCanWrite() {
			return canWrite;
		}

		public void setCanWrite(Boolean canWrite) {
			this.canWrite = canWrite;
		}

		public Boolean getCanApprove() {
			return canApprove;
		}

		public void setCanApprove(Boolean canApprove) {
			this.canApprove = canApprove;
		}
	}

	public static class WoList {
		private String id;
		private String rootId;
		private String name;
		private List<WoPath> path = new ArrayList<>();
		private List<WoFolder> folders = new ArrayList<>();
		private List<WoFile> files = new ArrayList<>();

		public String getId() {
			return id;
		}

		public void setId(String id) {
			this.id = id;
		}

		public String getRootId() {
			return rootId;
		}

		public void setRootId(String rootId) {
			this.rootId = rootId;
		}

		public String getName() {
			return name;
		}

		public void setName(String name) {
			this.name = name;
		}

		public List<WoPath> getPath() {
			return path;
		}

		public void setPath(List<WoPath> path) {
			this.path = path;
		}

		public List<WoFolder> getFolders() {
			return folders;
		}

		public void setFolders(List<WoFolder> folders) {
			this.folders = folders;
		}

		public List<WoFile> getFiles() {
			return files;
		}

		public void setFiles(List<WoFile> files) {
			this.files = files;
		}
	}

	public static class WoPath {
		private String id;
		private String name;

		public String getId() {
			return id;
		}

		public void setId(String id) {
			this.id = id;
		}

		public String getName() {
			return name;
		}

		public void setName(String name) {
			this.name = name;
		}
	}

	public static class WoFolder {
		private String id;
		private String name;
		private String updateTime;
		private String creator;

		public String getId() {
			return id;
		}

		public void setId(String id) {
			this.id = id;
		}

		public String getName() {
			return name;
		}

		public void setName(String name) {
			this.name = name;
		}

		public String getUpdateTime() {
			return updateTime;
		}

		public void setUpdateTime(String updateTime) {
			this.updateTime = updateTime;
		}

		public String getCreator() {
			return creator;
		}

		public void setCreator(String creator) {
			this.creator = creator;
		}
	}

	public static class WoFile {
		private String id;
		private String name;
		private String extension;
		private Long length;
		private String updateTime;

		public String getId() {
			return id;
		}

		public void setId(String id) {
			this.id = id;
		}

		public String getName() {
			return name;
		}

		public void setName(String name) {
			this.name = name;
		}

		public String getExtension() {
			return extension;
		}

		public void setExtension(String extension) {
			this.extension = extension;
		}

		public Long getLength() {
			return length;
		}

		public void setLength(Long length) {
			this.length = length;
		}

		public String getUpdateTime() {
			return updateTime;
		}

		public void setUpdateTime(String updateTime) {
			this.updateTime = updateTime;
		}
	}

	public static class WoConsign extends WoId {
		private static final long serialVersionUID = 1L;
		private Integer copiedFiles;
		private Integer copiedFolders;

		public Integer getCopiedFiles() {
			return copiedFiles;
		}

		public void setCopiedFiles(Integer copiedFiles) {
			this.copiedFiles = copiedFiles;
		}

		public Integer getCopiedFolders() {
			return copiedFolders;
		}

		public void setCopiedFolders(Integer copiedFolders) {
			this.copiedFolders = copiedFolders;
		}
	}

	public static class WoRequest extends WoId {
		private static final long serialVersionUID = 1L;
		private String targetKind;
		private String targetId;
		private String targetName;
		private String targetPath;
		private String applicant;
		private String reason;
		private String status;
		private String approver;
		private String approveTime;
		private String note;
		private String createTime;
		private Boolean mine;
		private Boolean canApprove;

		public String getTargetKind() {
			return targetKind;
		}

		public void setTargetKind(String targetKind) {
			this.targetKind = targetKind;
		}

		public String getTargetId() {
			return targetId;
		}

		public void setTargetId(String targetId) {
			this.targetId = targetId;
		}

		public String getTargetName() {
			return targetName;
		}

		public void setTargetName(String targetName) {
			this.targetName = targetName;
		}

		public String getTargetPath() {
			return targetPath;
		}

		public void setTargetPath(String targetPath) {
			this.targetPath = targetPath;
		}

		public String getApplicant() {
			return applicant;
		}

		public void setApplicant(String applicant) {
			this.applicant = applicant;
		}

		public String getReason() {
			return reason;
		}

		public void setReason(String reason) {
			this.reason = reason;
		}

		public String getStatus() {
			return status;
		}

		public void setStatus(String status) {
			this.status = status;
		}

		public String getApprover() {
			return approver;
		}

		public void setApprover(String approver) {
			this.approver = approver;
		}

		public String getApproveTime() {
			return approveTime;
		}

		public void setApproveTime(String approveTime) {
			this.approveTime = approveTime;
		}

		public String getNote() {
			return note;
		}

		public void setNote(String note) {
			this.note = note;
		}

		public String getCreateTime() {
			return createTime;
		}

		public void setCreateTime(String createTime) {
			this.createTime = createTime;
		}

		public Boolean getMine() {
			return mine;
		}

		public void setMine(Boolean mine) {
			this.mine = mine;
		}

		public Boolean getCanApprove() {
			return canApprove;
		}

		public void setCanApprove(Boolean canApprove) {
			this.canApprove = canApprove;
		}
	}

	public static class WoApprove {
		private Boolean executed;
		private String status;
		private String targetName;

		public Boolean getExecuted() {
			return executed;
		}

		public void setExecuted(Boolean executed) {
			this.executed = executed;
		}

		public String getStatus() {
			return status;
		}

		public void setStatus(String status) {
			this.status = status;
		}

		public String getTargetName() {
			return targetName;
		}

		public void setTargetName(String targetName) {
			this.targetName = targetName;
		}
	}

	public static class WoConfig {
		private String holder;
		private List<String> writerPersonList = new ArrayList<>();
		private List<String> fallbackApproverPersonList = new ArrayList<>();
		private Boolean canEdit;

		public String getHolder() {
			return holder;
		}

		public void setHolder(String holder) {
			this.holder = holder;
		}

		public List<String> getWriterPersonList() {
			return writerPersonList;
		}

		public void setWriterPersonList(List<String> writerPersonList) {
			this.writerPersonList = writerPersonList;
		}

		public List<String> getFallbackApproverPersonList() {
			return fallbackApproverPersonList;
		}

		public void setFallbackApproverPersonList(List<String> fallbackApproverPersonList) {
			this.fallbackApproverPersonList = fallbackApproverPersonList;
		}

		public Boolean getCanEdit() {
			return canEdit;
		}

		public void setCanEdit(Boolean canEdit) {
			this.canEdit = canEdit;
		}
	}

	@SuppressWarnings("unused")
	private static final Map<String, String> EMPTY = new LinkedHashMap<>();
}
