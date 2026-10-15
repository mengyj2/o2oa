<script setup>
import {ref, onMounted, onUnmounted, nextTick, provide, inject, render, h, getCurrentInstance} from 'vue'
import {o2, lp} from "@o2oa/component";
import IMAside from "./components/IMAside.vue";
import IMMain from "./components/IMMain.vue";
import ChooseConversationPage from "./pages/ChooseConversationPage.vue";
import MsgHistoryPage from "./pages/MsgHistoryPage.vue";
import ImConfigPage from "./pages/ImConfigPage.vue";
import MyCollectionPage from "./pages/MyCollectionPage.vue";
import {EventName} from "./utils/eventBus.js";
import {getBaiduMapUrl, getImFileDownloadUrl, imAction, imConversationRead} from "./utils/actions.js";
import {editOffice, isOfficeEditable} from "./utils/imTool.js";
import {imConfig, imGlobalOptions, windowState} from './store.js';

// 获取主应用实例（确保在主应用挂载后调用）
const appInstance = getCurrentInstance()?.appContext;

const windowStateInstance = windowState();
const imConfigInstance = imConfig();
const imGlobalOptionsInstance = imGlobalOptions();
// eventBus
const eventBus = inject('eventBus')

// 外部传入的 options
const { options } = defineProps(['options'])

let openChooseConversationEventName = null

const resizeListener = ()=> windowStateInstance.updateWindowWidth()

onMounted(() => {
  window.addEventListener("resize", resizeListener)
  window.addEventListener("focus", onWindowFocus)
  resizeListener() // 初始化值
  // 根据 options 处理一些特殊情况 比如打开某一个会话
  console.debug('APP =====>  onMounted  options', options)
  // 默认打开的会话 openConversation 是一个 conversation 对象
  if (options && options.openConversation && options.openConversation.id && options.openConversation.personList) {
    openConversationForOutside(options.openConversation)
  } else if (options && options.chatToPerson) {
    chatToPerson(options.chatToPerson)
  }
  if (options) {
    hideSide.value = !!options.hideSide
    imGlobalOptionsInstance.setOptions({
      hideSide: !!options.hideSide
    })
    console.debug('APP =====>  imGlobalOptions', imGlobalOptionsInstance.hideSide)
  }

  // 打开会话选择器 data 里面应该包含 回调的eventName
  eventBus.subscribe(EventName.openChooseConversation, (data) => {
    console.debug("openChooseConversation", data)
    showChooseConversation.value = true
    openChooseConversationEventName = data.eventName
  })
  eventBus.subscribe(EventName.openMsg, (data) => {
    console.debug("openMsg", data)
    openMsg(data)
  })
  eventBus.subscribe(EventName.changeIMConfig, (data) => {
    console.debug("changeIMConfig", data)
    loadImConfig()
  })
  // 读取配置
  loadImConfig()
  // 监听 websocket 消息
  if (layout.desktop && layout.desktop.socket && layout.desktop.socket.addImListener) {
    console.debug('websocket 消息 addImListener => ')
    layout.desktop.socket.addImListener("im_revoke", imWsRevokeMessage);
    layout.desktop.socket.addImListener("im_create", imWsCreateMessage);
    layout.desktop.socket.addImListener("im_conversation", imWsConversationMessage);
  }
  if (layout.desktop) {
    if (!layout.desktop.im) {
      layout.desktop.im = {}
    }
    layout.desktop.im.openChat = openConversationForOutside
    layout.desktop.im.chatToPerson = chatToPerson
  }
})
onUnmounted(() => {
  window.removeEventListener("resize", resizeListener)
  window.removeEventListener("focus", onWindowFocus)
  if (_readTimer) {
    clearTimeout(_readTimer)
    _readTimer = null
  }
  // eventBus.unsubscribe(EventName.openConversation)
  eventBus.unsubscribe(EventName.openChooseConversation)
  eventBus.unsubscribe(EventName.openMsg)
  layout.desktop.im.openChat = undefined
  layout.desktop.im.chatToPerson = undefined
  console.debug('APP =========== > onUnmounted')
})

const chatToPerson = async (person) => {
  if (!person) {
    return
  }
  console.debug('APP === 》 chatToPerson', person)
  const conv = await imAction('create', {
    type: 'single',
    personList: [person],
  })
  if (conv) {
    openConversationForOutside(conv)
  }
}

// 打开会话 给外部调用
const openConversationForOutside = (conversation) => {
  console.debug('APP === 》 openConversationForOutside', conversation)
  if (!conversation) {
    return
  }
  nextTick(()=> {
    if (layout.desktop.apps && layout.desktop.apps["IMV2"] && layout.desktop.apps["IMV2"].setCurrent) {
      layout.desktop.apps["IMV2"].setCurrent();
    }
    if (conversation.personList && conversation.personList.contains(layout.session.user.distinguishedName)) {
      currentConversation.value = conversation
      eventBus.publish( EventName.initOpenedConversation, conversation)
      markConversationRead(conversation.id, true)
    } else {
      console.error('当前用户不能打开这个会话', conversation)
    }
  })
}
// 点击会话 打开聊天窗口
const openConversation = (conversation) => {
  console.debug("openConversation", conversation)
  currentConversation.value = conversation
  // ★ 打开即已读（乐观清零 + 上报后端）
  if (conversation && conversation.id) {
    markConversationRead(conversation.id, true)
  }
}
// 修改聊天信息对象
const updateOrDeleteConversation = ( conv ) => {
  console.debug("updateOrDeleteConversation", conv)
  currentConversation.value = conv
  eventBus.publish( EventName.refreshMyConversation ) // 刷新列表
}

provide('im-app', {
  openConversation,
  updateOrDeleteConversation
});

/**
 * ★ 会话已读同步（2026-10-15 源码级，根治「消息全读了，未读标记刷新不及时」）
 *
 * 旧实现的三个缺陷（均在本文件/补丁层）：
 *   ① 同一会话【15 秒】内只上报一次 ⇒ 停留会话中收到的新消息要等 15s 才可能被标已读；
 *   ② 只 publish(refreshMyConversation) 等接口回包，【无本地乐观清零】⇒ 回包前角标仍是旧值；
 *   ③ wsAddMsg 只追加消息、【不触发已读上报】⇒「我正看着的会话」也被计为未读。
 *
 * 新实现三段式：
 *   ① 本地乐观清零（角标立即消失，零等待）
 *   ② 上报后端 conversationRead（写 lastReadTime，服务端真值）
 *   ③ 服务端为准合并刷新（去抖 400ms，避免连点抖动）
 * 触发点：打开会话 / 正在会话中收到新消息 / 窗口重新聚焦。
 */
let _readAt = {};
let _readTimer = null;
const markConversationRead = (conversationId, force) => {
  if (!conversationId) {
    return;
  }
  const now = Date.now();
  // 去抖：同一会话 1.2s 内不重复上报（旧实现 15s 过长，正是"读完迟迟不消失"的直接原因）
  if (!force && _readAt[conversationId] && (now - _readAt[conversationId]) < 1200) {
    return;
  }
  _readAt[conversationId] = now;
  // ① 本地乐观清零
  eventBus.publish(EventName.conversationReadLocal, conversationId);
  refreshTopBadge(conversationId);
  // ② 上报后端
  imConversationRead(conversationId).then(() => {
    // ③ 以服务端为准（合并多次触发）
    if (_readTimer) {
      clearTimeout(_readTimer);
    }
    _readTimer = setTimeout(() => {
      _readTimer = null;
      eventBus.publish(EventName.refreshMyConversation, 'read');
      refreshTopBadge(conversationId);
    }, 400);
  }).catch((e) => {
    console.debug('标记已读失败', conversationId, e);
  });
};
// 顶栏「聊聊」未读角标由 x_desktop/js/o2im_topbadge.js 维护（桌面框架层），此处两路联动刷新：
//   ① window.__o2ImTopBadgeRefresh —— 早期约定，兼容仍在用；
//   ② 标准 DOM 事件 o2-im-read —— 解耦通道，桌面层脚本/Badge 只要监听即可，无需耦合 IMV2 内部符号。
const refreshTopBadge = (conversationId) => {
  try {
    if (window.__o2ImTopBadgeRefresh) {
      window.__o2ImTopBadgeRefresh();
    }
  } catch (e) { /* ignore */ }
  try {
    window.dispatchEvent(new CustomEvent('o2-im-read', {detail: {conversationId: conversationId}}));
  } catch (e) { /* ignore */ }
};
// 窗口重新聚焦 ⇒ 补一次已读（用户切走又切回，期间可能来了新消息）
const onWindowFocus = () => {
  if (currentConversation.value && currentConversation.value.id) {
    markConversationRead(currentConversation.value.id, true);
  }
};

// websocket 创建消息
const imWsCreateMessage = (msg) => {
  console.debug('websocket 消息 创建=====> ', msg)
  eventBus.publish( EventName.wsAddMsg, msg )
  eventBus.publish( EventName.refreshMyConversation ) // 刷新列表
  // ★ 正在查看的会话来了新消息 ⇒ 立即标记已读，避免角标"在眼皮底下"继续增长
  if (msg && currentConversation.value && msg.conversationId === currentConversation.value.id) {
    markConversationRead(msg.conversationId, true)
  }
}
// websocket 撤回消息
const imWsRevokeMessage = (msg) => {
  console.debug('websocket 消息 撤回=====> ', msg)
  eventBus.publish( EventName.wsRevokeMsg, msg )
}
// websocket 会话更新消息
const imWsConversationMessage = (conversation) => {
  console.debug('websocket 消息 会话更新=====> ', conversation)
  eventBus.publish( EventName.refreshMyConversation ) // 刷新列表
}

const hideSide = ref(false)

const currentConversation = ref(null)

const showChooseConversation = ref(false)

const closeChooseConversation = (conversation) => {
  console.debug('APP === 》 closeChooseConversation', conversation)
  showChooseConversation.value = false
  if (conversation && openChooseConversationEventName) {
    eventBus.publish(openChooseConversationEventName, conversation)
  }
}
const loadImConfig = async () => {
  const config = await imAction('getImConfig')
  imConfigInstance.setImConfig(config)
}
/**
 * ★ 文件消息打开（2026-10-15 源码级实现）
 *
 * 官方旧行为：office 类型 → OnlyOffice【只读预览】(mode:"view")；其它 → 直接触发下载。
 * 本实现：
 *   · 可编辑 office（doc/docx/xls/xlsx/ppt/pptx/csv/txt…）→ editOffice()
 *       —— 下载附件二进制 → POST /x_onlyofficefile_assemble_control/jaxrs/onlyoffice/upload
 *          → 以【可编辑】模式打开；编辑器按 syncDrive 选项在保存/关闭时回存「个人网盘」。
 *   · 其它类型（图片/PDF/音视频/文本/未知）→ 通用预览 UniversalPreview，兜底 window.open。
 *   ★ 能力本体在 src/utils/imTool.js（源码模块，随构建进入 main.js），
 *     不再依赖构建期注入的 $Main/default/o2im.js。
 */
const openFileMsg = (body) => {
  const ext = (body.fileExtension || "").toLowerCase();
  const url = getImFileDownloadUrl(body.fileId);
  const name = body.fileName || "file";
  if (isOfficeEditable(ext)) {
    editOffice({url: url, name: name, ext: ext, size: body.fileSize, fromIM: body.fileId});
    return;
  }
  const cfg = {
    url: url, name: name, ext: ext, size: body.fileSize,
    token: (window.layout && layout.session ? layout.session.token : "")
  };
  if (window.o2 && window.o2.o2Preview) {
    window.o2.o2Preview.open(cfg);
    return;
  }
  window.o2.load("/x_component_UniversalPreview/preview.js", () => {
    if (window.o2.o2Preview) {
      window.o2.o2Preview.open(cfg);
    } else {
      // 兜底：预览组件不可用时不至于点了没反应
      window.open(url);
    }
  });
}

// 打开消息
const openMsg = (msg) => {
  const body = JSON.parse(msg.body)
  if (body.type === 'messageHistory') {
    openMsgHistory(msg)
  } else if (body.type === "image") {
    _openImageView(getImFileDownloadUrl(body.fileId))
    // window.open(getImFileDownloadUrl(body.fileId))
  } else if (body.type === "process") {
    if (body.work) {
      o2.api.form.openWork(body.work, "", "");
    }
  }  else if (body.type === "cms") {
    if (body.docId) {
      o2.api.form.openDocument(body.docId);
    }
  } else if (body.type === "file") {
    openFileMsg(body);
  } else if (body.type === "location") {
    const url = getBaiduMapUrl(body.latitude, body.longitude, body.address, body.addressDetail);
    window.open(url);
  } else if (body.type === "link") {
    if (body.linkUrl) {
      window.open(body.linkUrl);
    }
  }
}
// 图片预览 功能
let _imageViewer;
const _openImageView = (imageUrl) => {
  const imgNode = document.createElement("img");
  imgNode.src = imageUrl;
  document.body.appendChild(imgNode);
  imgNode.style.display = "none";
  o2.loadCss("../o2_lib/viewer/viewer.css", document.body, () => {
    o2.load("../o2_lib/viewer/viewer.js", ()=> {
      _imageViewer = new Viewer(imgNode,{
        navbar : false,
        toolbar : true,
        hidden : () => {
          imgNode.remove();
          _imageViewer.destroy();
        }
      });
      _imageViewer.show();
    })
  })
}
// 打开聊天记录类型的消息
const openMsgHistory = async (msg) => {
  const container = document.querySelector('.im-container')
    // const fragment = document.createDocumentFragment()
    // const msgHistoryPageComponent = createApp(MsgHistoryPage, {
    //   msg: msg
    // }).mount(fragment)
  // 创建一个容器元素
  const el = document.createElement('div');
  // 通过主应用的 context 创建 vnode
  const vnode = h(MsgHistoryPage);
  vnode.props = {
    msg: msg
  }
  // ** 关键代码，继承主应用的 appContext **
  if (appInstance) {
    vnode.appContext = appInstance;
  }
  // 将 vnode 渲染到 el
  render(vnode, el);
  $OOUI.dialog(lp.msgHistory, el, container, {buttons: '', canMove: false})
}
// 打开设置页面
const openImConfigPage = () => {
  const container = document.querySelector('.im-container')
  // const fragment = document.createDocumentFragment()
  // const imConfigPage = createApp(ImConfigPage, {}).mount(fragment)
  // 创建一个容器元素
  const el = document.createElement('div');
  // 通过主应用的 context 创建 vnode
  const vnode = h(ImConfigPage);
  // ** 关键代码，继承主应用的 appContext **
  if (appInstance) {
    vnode.appContext = appInstance;
  }
  // 将 vnode 渲染到 el
  render(vnode, el);
  $OOUI.dialog(lp.setting, el, container, {buttons: '', canMove: false})
}
// 打开我的收藏页码
const openMyCollectionPage = () => {
  const container = document.querySelector('.im-container')
  // 创建一个容器元素
  const el = document.createElement('div');
  // 通过主应用的 context 创建 vnode
  const vnode = h(MyCollectionPage);
  // ** 关键代码，继承主应用的 appContext **
  if (appInstance) {
    vnode.appContext = appInstance;
  }
  // 将 vnode 渲染到 el
  render(vnode, el);
  $OOUI.dialog(lp.msgCollectionTitle, el, container, {buttons: '', canMove: false})
}
</script>

<template>
  <div class="im-app im-container" :class=" windowStateInstance.isMobile ? 'im-app-s' : '' ">
    <div class="im-aside" :class="{ hidden: windowStateInstance.isMobile && currentConversation, w100:  windowStateInstance.isMobile}" v-if="!hideSide" >
      <IMAside @clickImConfig="openImConfigPage" @clickMyCollectionPage="openMyCollectionPage"/>
    </div>
    <div class="im-main">
      <IMMain :conv="currentConversation"/>
    </div>
  </div>
  <ChooseConversationPage v-if="showChooseConversation"
                          @closeChooseConversation="closeChooseConversation"></ChooseConversationPage>
</template>

<style scoped></style>
