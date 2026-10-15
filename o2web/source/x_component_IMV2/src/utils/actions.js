import {o2} from '@o2oa/component';

/**
 * 查询公共配置
 * @param {*} name
 * @returns
 */
function getPublicData(name) {
    return new Promise((resolve) => {
        o2.UD.getPublicData(name, (dData) => resolve(dData));
    });
}
/**
 * 设置公共配置
 * @param {*} name
 * @param {*} value
 * @returns
 */
function putPublicData(name, value) {
    return new Promise((resolve) => {
        o2.UD.putPublicData(name, value, (dData) => resolve(dData));
    });
}

/**
 * 调用后端api 只返回data
 * @param {*} content
 * @param {*} action
 * @param {*} method
 * @param  {...any} args
 * @returns
 */
async function doAction(content, action, method, ...args) {
    const m = o2.Actions.load(content)[action][method];
    const json = await m.apply(m, ...args);
    return json.data;
}
/**
 * 调用后端api 返回整个response对象
 * @param {*} content
 * @param {*} action
 * @param {*} method
 * @param  {...any} args
 * @returns
 */
async function doActionBackResult(content, action, method, ...args) {
    const m = o2.Actions.load(content)[action][method];
    return await m.apply(m, ...args);
}

/**
 * 组织管理 人员 API
 * x_organization_assemble_control
 * @param {*} method
 * @param  {...any} args
 * @returns
 */
function personAction(method, ...args) {
    return doAction('x_organization_assemble_control', 'PersonAction', method, args);
}

/**
 * 个人 API PersonAction
 * x_organization_assemble_personal
 * @param {*} method
 * @param  {...any} args
 * @returns
 */
function personalAction(method, ...args) {
    return doAction('x_organization_assemble_personal', 'PersonAction', method, args);
}

/**
 * UnitAction
 * x_organization_assemble_control
 * @param method
 * @param args
 * @returns {Promise<*>}
 */
function orgUnitAction(method, ...args) {
    return doAction('x_organization_assemble_control', 'UnitAction', method, args);
}
/**
 * PersonAction
 * x_organization_assemble_control
 * @param method
 * @param args
 * @returns {Promise<*>}
 */
function orgPersonAction(method, ...args) {
    return doAction('x_organization_assemble_control', 'PersonAction', method, args);
}
/**
 * IdentityAction
 * x_organization_assemble_control
 * @param method
 * @param args
 * @returns {Promise<*>}
 */
function orgIdentityAction(method, ...args) {
    return doAction('x_organization_assemble_control', 'IdentityAction', method, args);
}

/**
 * UnitAction
 * x_organization_assemble_express
 * @param method
 * @param args
 * @returns {Promise<*>}
 */
function orgExpressUnitAction(method, ...args) {
    return doAction('x_organization_assemble_express', 'UnitAction', method, args);
}

/**
 * ★ 身份DN(@I) → 人员DN(@P) 归一【2026-10-15 源码级，原为构建期注入】
 *
 * 背景：IM 会话可见性按【人员DN(@P)】匹配当前人，但上游（流程协同 chatToPerson、
 *       getProcessReviewByJobId 等）传入的可能是【身份DN(@I)】。
 * ★ 本实例身份 unique 段【带单位前缀】：
 *     身份 孟弋洁@51100000500009247D_mengyijie@I
 *     人员 孟弋洁@mengyijie@P
 *   二者 unique 段不同，仅改尾字符无效 ⇒ 必须取 unique 段【最后一段】(人员unique) 重新拼接。
 * 不归一的后果：收件人匹配不到自己的 @P ⇒ 整个会话对他不可见 ⇒
 *   「对方发来的消息/文件我完全没收到」（消息实际在服务端）。
 * @param {string} dn
 * @returns {string}
 */
function normalizeImPersonDn(dn) {
    try {
        if (typeof dn !== 'string' || dn.slice(-2) !== '@I') {
            return dn;
        }
        const p = dn.split('@');
        if (p.length !== 3) {
            return dn;
        }
        return p[0] + '@' + p[1].split('_').pop() + '@P';
    } catch (e) {
        return dn;
    }
}

/**
 * 聊聊 API（统一出口）
 * ★ 在出口处对 create 的成员列表做 @I→@P 归一，覆盖全部调用方（含流程协同）。
 * @param {*} method
 * @param  {...any} args
 * @returns
 */
function imAction(method, ...args) {
    if (method === 'create' && args[0] && Array.isArray(args[0].personList)) {
        args[0].personList = args[0].personList.map(normalizeImPersonDn);
    }
    return doAction('x_message_assemble_communicate', 'ImAction', method, args);
}

/**
 * 标记会话已读（后端 ActionConversationRead → PUT /jaxrs/im/conversation/{id}/read）。
 * ★ 官方前端【从不调用】本接口 ⇒ IMConversationExt.lastReadTime 不更新 ⇒
 *   会话列表/顶栏的 unreadNumber 只增不减、角标永不清零。
 * @param {string} conversationId
 * @returns {Promise}
 */
function imConversationRead(conversationId) {
    if (!conversationId) {
        return Promise.resolve();
    }
    return imAction('conversationRead', conversationId);
}

/**
 * 聊聊上传 Promise
 * @param conversationId
 * @param type
 * @param formData
 * @param file 文件对象
 * @param progressCallback 进度返回函数
 * @returns {Promise<unknown>}
 */
function imUploadFile(conversationId, type, formData, file, progressCallback) {
    return new Promise((res, rej) => {
        const action = o2.Actions.load('x_message_assemble_communicate').ImAction;
        action.action.targetModule = {
            module: {
                addFormDataMessage: (file) => {
                    console.log('创建进度条', file);
                    //返回一个对象，用于处理进度条
                    return {
                        //在上传完成，失败或取消时，清除进度条
                        clearMessageProgress: () => {
                            console.log('清除进度条', file);
                        },
                        //更新进度条
                        updateProgress: (progress) => {
                            console.log('更新进度条', file, progress);
                            if (progressCallback) {
                                progressCallback(progress)
                            }
                        },
                        //更新进度条标题
                        setMessageTitle: (title) => {
                            console.log('更新进度条标题', file, title);
                        },
                        //更新进度条文本
                        setMessageText: (text) => {
                            console.log('更新进度条文本', file, text);
                        },
                        //开始上传
                        transferStart: () => {
                            console.log('开始上传', file);
                        },

                        //上传失败
                        transferFailed: () => {
                            console.log('上传失败', file);
                        },

                        //上传取消
                        transferCanceled: () => {
                            console.log('上传取消', file);
                        },

                        //上传完成
                        transferComplete: () => {
                            console.log('上传完成', file);
                        },

                        //这个data为了兼容，防止代码报错，实际上并没有用到
                        data: {id: ''},
                    };
                },
            },
            file: file,
        };

        action.uploadFile(
            conversationId,
            type,
            formData,
            file,
            (json) => {
                if (json.data) {
                    res(json.data);
                } else {
                    res(undefined);
                }
            },
            (error) => {
                console.error(error);
                rej(error);
            },
        );

        // o2.Actions.load("x_message_assemble_communicate").ImAction.uploadFile(conversationId, type, formData, file,  (json)=> {
        //   if (json.data) {
        //     res(json.data)
        //   } else {
        //     res(undefined)
        //   }
        // },  (error)=> {
        //   console.error(error)
        //   rej(error)
        // })
    });
}

/**
 * 获取头像 url
 * 默认是群聊头像
 * @param person
 * @returns {*}
 */
function getAvatarUrl(person) {
    const orgAction = o2.Actions.get('x_organization_assemble_control');
    return person ? orgAction.getPersonIcon(person) : new URL('../assets/group.png', import.meta.url).href;
}

/**
 * 会话头像 url
 * @param conversationId
 * @returns {string}
 */
function conversationIconUrl(conversationId) {
    const action = o2.Actions.get('x_message_assemble_communicate').action;
    let url = action.getAddress() + '/jaxrs/im/conversation/{id}/icon';
    url = url.replace('{id}', encodeURIComponent(conversationId));
    url += '?' + new Date().getTime();
    return url;
}

//图片 根据大小 url
const getImFileUrlWithWH = (id, width, height) => {
    const action = o2.Actions.get('x_message_assemble_communicate').action;
    let url = action.getAddress() + action.actions.imgFileDownloadWithWH.uri;
    url = url.replace('{id}', encodeURIComponent(id));
    url = url.replace('{width}', encodeURIComponent(width));
    url = url.replace('{height}', encodeURIComponent(height));
    return url;
};
//file 下载的url
const getImFileDownloadUrl = (id) => {
    var action = o2.Actions.get('x_message_assemble_communicate').action;
    var url = action.getAddress() + action.actions.imgFileDownload.uri;
    url = url.replace('{id}', encodeURIComponent(id));
    return url;
};

//百度地图打开地址
const getBaiduMapUrl = (lat, longt, address, content) => {
    return (
        'https://api.map.baidu.com/marker?location=' +
        lat +
        ',' +
        longt +
        '&title=' +
        address +
        '&content=' +
        content +
        '&output=html&src=net.o2oa.map'
    );
};

export {
    doAction,
    doActionBackResult,
    orgUnitAction,
    orgPersonAction,
    orgExpressUnitAction,
    orgIdentityAction,
    getPublicData,
    putPublicData,
    personAction,
    personalAction,
    imAction,
    imConversationRead,
    normalizeImPersonDn,
    imUploadFile,
    getAvatarUrl,
    getImFileUrlWithWH,
    getImFileDownloadUrl,
    getBaiduMapUrl,
    conversationIconUrl,
};
