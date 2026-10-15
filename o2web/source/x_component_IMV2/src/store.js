import {defineStore} from 'pinia';
import {imAction, imUploadFile} from "./utils/actions.js";
import {canUseWebP, ymdhms} from "./utils/common.js";
import {lp} from "@o2oa/component";
import {uuid} from "@o2oa/util";

export const windowState = defineStore('windowState', {
    state: () => ({
        windowWidth: window.innerWidth, // 窗口宽度
        isMobile: false
    }),
    actions: {
        updateWindowWidth() {
            this.windowWidth = window.innerWidth;
            this.isMobile = this.windowWidth < 768
            console.debug('=====> update ' + this.isMobile + ' windowWidth' + this.windowWidth);
        }
    }
})

export const useLoadingStore = defineStore('loading', {
    state: () => ({
        isLoading: false,
        loadingText: '加载中...'
    }),
    actions: {
        showLoading(text) {
            this.isLoading = true;
            if (text) {
                this.loadingText = text;
            }
        },
        hideLoading() {
            this.isLoading = false;
        }
    }
});

export const imConfig = defineStore('imConfig', {
    state: () => ({
        enableClearMsg: false,
        enableRevokeMsg: false,
        enableOnlyOfficePreview: false,
        enableGroupMemberQuitSelf: false,
        revokeOutMinute: 2,
        conversationCheckInvoke: '',
    }),
    actions: {
        setImConfig(config) {
            this.enableClearMsg = config.enableClearMsg ?? false;
            this.enableRevokeMsg = config.enableRevokeMsg ?? false;
            this.enableOnlyOfficePreview= config.enableOnlyOfficePreview ?? false;
            this.enableGroupMemberQuitSelf= config.enableGroupMemberQuitSelf ?? false;
            this.revokeOutMinute= config.revokeOutMinute ?? 2;
            this.conversationCheckInvoke= config.conversationCheckInvoke ?? '';
        }
    }
})

export const imGlobalOptions = defineStore('imGlobalOptions', {
    state: () => ({
        hideSide: false,
        firstOpenConversation: true,
    }),
    actions: {
        setOptions(options)  {
            this.hideSide = options.hideSide ?? false
        },
        loadedConversation() {
            this.firstOpenConversation = false
        }
    }
})

/**
 * ★ 上传队列（2026-10-15 源码级重写，对齐微信的「有进度 / 有结果 / 不重发」体验）
 *
 * 旧实现的四个缺陷（用户反馈「上传附件没有进度和完成提醒，刷新也不及时，
 * 导致上传好几次」）：
 *   ① 上传成功后【只 console.log】，既不 publish 刷新会话列表，也不提示用户
 *      ⇒ 发送者自己看不到「已发出去」的反馈，于是反复点；
 *   ② 上传失败/中断时进度条被【无条件 splice 掉】，用户只看到进度条消失，
 *      分不清「成功」还是「失败」；
 *   ③ 没有并发去重 ⇒ 连点两次就把同一个文件传两遍、发两条消息；
 *   ④ 进度项只有 name/progress，没有状态，无法区分上传中 / 已完成 / 失败。
 *
 * 新模型：每条上传项是一个小状态机
 *   status: 'uploading' → 'done'（1.5s 后自动消失）/ 'error'（保留，可重试或移除）
 *   并携带 conversationId / rawFile，支持重试与按会话归组。
 *   返回值约定：{ ok, message?, duplicate?, error? }，由调用方（IMMain）负责提示。
 */
export const uploadFileList = defineStore('uploadFileList', {
    state: () => ({
        uploadFileList: [],
    }),
    actions: {
        /**
         * 上传并发送为聊天文件消息。
         * @param {File} file
         * @param {string} conversationId
         * @returns {Promise<{ok:boolean, message?:object, duplicate?:boolean, error?:string}>}
         */
        async addUploadFileAndSendMessage (file, conversationId)  {
            if (!file || !conversationId) {
                console.error('没有传入 file 或者 conversationId')
                return {ok: false, error: '缺少文件或会话信息'}
            }
            // ① 并发去重：同一会话内同名文件正在上传 ⇒ 忽略本次（防「点好几次」重发）
            const dup = this.uploadFileList.find((m) =>
                m.conversationId === conversationId && m.name === file.name && m.status === 'uploading')
            if (dup) {
                return {ok: false, duplicate: true, error: '「' + file.name + '」正在上传中，请稍候…'}
            }
            const formData = new FormData();
            formData.append('file', file);
            formData.append('fileName', file.name);
            const fileExt = file.name.substring(file.name.lastIndexOf('.'));
            // 图片消息
            let type;
            if (fileExt.toLowerCase() === '.webp' && canUseWebP()) {
                type = 'image';
            } else if (
                fileExt.toLowerCase() === '.bmp' ||
                fileExt.toLowerCase() === '.jpeg' ||
                fileExt.toLowerCase() === '.png' ||
                fileExt.toLowerCase() === '.jpg'
            ) {
                type = 'image';
            } else {
                // 文件消息
                type = 'file';
            }
            const fileId = `${uuid()}`
            this.uploadFileList.push({
                id: fileId,
                name: file.name,
                size: file.size,
                progress: 0,
                status: 'uploading',
                error: '',
                conversationId: conversationId,
                rawFile: file,
            })

            const findItem = () => this.uploadFileList.find((m) => m.id === fileId);
            try {
                //上传文件
                const res = await imUploadFile(conversationId, type, formData, file, (progress)=> {
                    // 更新进度条（框架回调已是 0–100 的百分数，这里只做兜底钳制）
                    const data = findItem();
                    if (data) {
                        const p = Number(progress);
                        data.progress = isNaN(p) ? 0 : Math.max(0, Math.min(100, Math.round(p)));
                    }
                });
                if (!res || !res.id) {
                    throw new Error('服务端未返回文件标识');
                }
                const body = {
                    body: type === 'image' ? lp.msgTypeImage : lp.file,
                    type: type,
                    fileId: res.id,
                    fileExtension: res.fileExtension,
                    fileName: res.fileName,
                };
                const message = {
                    id: `${uuid()}`,
                    conversationId: conversationId,
                    body: JSON.stringify(body),
                    createPerson: layout.session.user.distinguishedName,
                    createTime: ymdhms(new Date()),
                    sendStatus: 1,
                };
                const result = await imAction('msgCreate', message);
                if (!result) {
                    throw new Error('消息发送失败');
                }
                // ② 成功：置 done（进度条走满 + 绿色对勾），1.5s 后自动消失
                const data = findItem();
                if (data) {
                    data.progress = 100;
                    data.status = 'done';
                    data.error = '';
                }
                setTimeout(() => this.removeUploadFile(fileId), 1500);
                return {ok: true, message: message, type: type, file: res};
            } catch (e) {
                // ③ 失败：保留进度项并标记 error，让用户能看见「失败」而不是「凭空消失」
                const msg = (e && e.message) ? e.message : (typeof e === 'string' ? e : '上传失败');
                const data = findItem();
                if (data) {
                    data.status = 'error';
                    data.error = msg;
                }
                console.error('上传附件失败', e);
                return {ok: false, error: msg};
            }
        },
        /** 从上传队列移除一项（取消上传 / 手动移除失败项）。 */
        removeUploadFile(fileId) {
            const i = this.uploadFileList.findIndex((m) => m.id === fileId);
            if (i > -1) {
                this.uploadFileList.splice(i, 1);
            }
        },
        /** 重试失败项：移除旧项后按原文件重新走一遍上传发送。 */
        retryUpload(fileId) {
            const item = this.uploadFileList.find((m) => m.id === fileId);
            if (!item || !item.rawFile) {
                return {ok: false, error: '原始文件已不可用，请重新选择'}
            }
            const file = item.rawFile;
            const conversationId = item.conversationId;
            this.removeUploadFile(fileId);
            return this.addUploadFileAndSendMessage(file, conversationId);
        }
    }
})
