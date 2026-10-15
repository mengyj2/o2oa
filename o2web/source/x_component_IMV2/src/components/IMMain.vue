<script setup>
import {ref, watch, nextTick, useTemplateRef, onMounted, onUnmounted, inject} from 'vue';
import {lp} from '@o2oa/component';
import {
  chooseSingleFile, containsUrl,
  conversationPicker, convertUrlToMarkdown,
  createContextMenu,
  formatPersonName,
  needClickMsg,
  toDate,
  ymdhms
} from '../utils/common.js';
import { marked } from "../utils/marked.esm.js";
import {imAction} from '../utils/actions.js';
import {pickDrive, toast, fmtSize} from '../utils/imTool.js';
import ChatMsg from './ChatMsg.vue';
import ChatInfo from './ChatInfo.vue';
import EmojiPicker from './EmojiPicker.vue';
import {contentEscapeBackToSymbol} from '../utils/escapeSymbol.js';
import {uuid} from '@o2oa/util';
import {EventName} from '../utils/eventBus.js';
import {imConfig, imGlobalOptions, uploadFileList, windowState} from '../store.js';

const imConfigInstance = imConfig();
const uploadFileListInstance = uploadFileList();
const imGlobalOptionsInstance = imGlobalOptions();
const windowStateInstance = windowState();
// eventBus
const eventBus = inject('eventBus');

const {openConversation} = inject('im-app')

const {conv} = defineProps(['conv']);

const hideSide = ref(false);

const conversation = ref(null);

const chatBodyNodeRef = useTemplateRef('chatBodyNodeRef');
// 是否选择模式
const chooseMode = ref(false);
// 输入的文字消息
const inputMsg = ref('');
// 是否在加载数据中
const isLoading = ref(false);
// 是否有更多数据
const hasMoreMsgData = ref(false);
// 消息列表
const msgList = ref([]);
//
const msgNode = ref();
// 选择的消息数据
const msgSelectedList = ref([]);
// 消息分页查询
const page = ref(1);
// 引用消息
const quoteMessage = ref(null);
// 选择表情
const showEmoji = ref(false);
//
const showChatInfo = ref(false);

onMounted(() => {
  eventBus.subscribe(EventName.wsAddMsg, (msg) => {
    console.debug('wsAddMsg', msg);
    if (!conversation.value) {
      return
    }
    if (msg && msg.conversationId === conversation.value.id) {
      const index = msgList.value.findIndex((e) => e.id === msg.id);
      if (index < 0) {
        msgList.value.push(msg);
        scrollToBottom();
      }
    }
  });
  eventBus.subscribe(EventName.wsRevokeMsg, (msg) => {
    console.debug('wsRevokeMsg', msg);
    if (!conversation.value) {
      return
    }
    if (msg && msg.conversationId === conversation.value.id) {
      const index = msgList.value.findIndex((e) => e.id === msg.id);
      if (index > -1) {
        msgList.value.splice(index, 1);
      }
    }
  });
  addDragEvents();
});
onUnmounted(() => {
  eventBus.unsubscribe(EventName.wsAddMsg);
  eventBus.unsubscribe(EventName.wsRevokeMsg);
  removeDragEvents();
});

watch(
    () => conv,
    (newConversation, old) => {
      console.debug('conv change', newConversation, old);
      conversation.value = newConversation;
      initMainPage();
    },
);

const quoteDescRef = useTemplateRef('quoteDescRef');

watch(quoteMessage, async () =>  {
  await nextTick() // 等待DOM 更新完成
  const links = quoteDescRef.value?.querySelectorAll('a')
  if (links && links.length) {
    links.forEach(link => {
      if (!link.hasAttribute('target')) {
        link.setAttribute('target', '_blank')
        link.setAttribute('rel', 'noopener noreferrer')
      }
    })
  }
});

// 事件组合
const eventMap = {
  dragenter: (e) => unionEvents('dragenter', e),
  dragover: (e) => unionEvents('dragover', e),
  dragleave: (e) => unionEvents('dragleave', e),
  drop: (e) => unionEvents('drop', e),
  paste: (e) => unionEvents('paste', e),
};

// method
// 添加事件绑定
const addDragEvents = () => {
  const mainNode = document.querySelector('.im-main');
  // 绑定拖拽事件，拖拽上传文件 发送文件消息
  for (let eventMapKey in eventMap) {
    mainNode.addEventListener(eventMapKey, eventMap[eventMapKey]);
  }
};
// 删除事件绑定
const removeDragEvents = () => {
  const mainNode = document.querySelector('.im-main');
  for (let eventMapKey in eventMap) {
    mainNode.removeEventListener(eventMapKey, eventMap[eventMapKey]);
  }
};
// 多个事件统一处理
const unionEvents = (eventName, e) => {
  console.debug(`unionEvents ================> ${eventName}`);
  // 阻止默认行为（防止文件打开）
  if (eventName !== 'paste') {
    e.preventDefault();
    e.stopPropagation();
  }
  if (!conversation.value) {
    return;
  }
  switch (eventName) {
    case 'dragenter':
      dragEnterOverEvent(e);
      break;
    case 'dragover':
      dragEnterOverEvent(e);
      break;
    case 'dragleave':
      dragLeaveEvent(e);
      break;
    case 'drop':
      dragLeaveEvent(e);
      dragDropFileSendMsg(e);
      break;
    case 'paste':
      pasteFileSendMsg(e);
      break;
  }
};
// 拖入/离开时的样式变化
const dragEnterOverEvent = () => {
  console.debug(`dragEnterOverEvent ================>`);
  const chatNode = document.querySelector('.im-chat');
  chatNode.classList.add('im-drag-style');
};
const dragLeaveEvent = () => {
  console.debug(`dragLeaveEvent ================>`);
  const chatNode = document.querySelector('.im-chat');
  chatNode.classList.remove('im-drag-style');
};
// 拖入文件发送消息
const dragDropFileSendMsg = (e) => {
  console.debug(`dragDropFileSendMsg ================>`);
  if (e && e.dataTransfer && e.dataTransfer.files) {
    const files = e.dataTransfer.files;
    console.debug('拖拽了文件', files);
    [...files].forEach((file) => {
      if (file.type && file.type !== '') {
        _sendFileMsg(file);
      }
    });
  }
};
// 从剪贴板 复制文件 发送消息
const pasteFileSendMsg = (e) => {
  if (!e || !e.clipboardData || !e.clipboardData.items) {
    return;
  }
  console.debug(`pasteFileSendMsg ================>`);
  // 获取粘贴的内容
  const items = e.clipboardData.items;
  // 遍历剪贴板中的所有项目
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    // 判断是否为文件类型
    if (item.kind === 'file') {
      const file = item.getAsFile();
      if (file) {
        console.debug('粘贴的文件:', file);
        _sendFileMsg(file);
      }
    } else if (item.type.indexOf('image') > -1) {
      // 处理图片类型，可以通过 getAsFile 获取 Blob 对象
      const file = item.getAsFile();
      if (file) {
        console.debug('粘贴的图片:', file);
        _sendFileMsg(file);
      }
    }
  }
};
// 关闭当前页面
const closeMainPage = () => {
  openConversation(null)
}
// 初始化数据
const initMainPage = async () => {
  console.debug('imGlobalOptions', imGlobalOptionsInstance.hideSide);
  hideSide.value = imGlobalOptionsInstance.hideSide;
  msgSelectedList.value = [];
  chooseMode.value = false;
  showChatInfo.value = false;
  hasMoreMsgData.value = false;
  isLoading.value = false;
  quoteMessage.value = null;
  inputMsg.value = '';
  msgList.value = [];
  page.value = 1;
  await loadMsgByPage();
};

const loadMoreMsgData = () => {
  if (!hasMoreMsgData.value) {
    return;
  }
  page.value += 1;
  loadMsgByPage();
};
//
const loadMsgByPage = async () => {
  if (!conversation.value || !conversation.value.id) {
    console.info(' conversation 已清空', conversation.value);
    return;
  }
  if (isLoading.value) {
    return;
  }
  isLoading.value = true;
  const data = {conversationId: conversation.value.id};
  const list = await imAction('msgListByPaging', page.value, 20, data);
  if (list && list.length > 0) {
    const newList = list.reverse();
    if (page.value > 1) {
      msgList.value.unshift(...newList);
    } else {
      msgList.value = newList;
      // 滚动到底部
      scrollToBottom();
    }
    hasMoreMsgData.value = list.length >= 20;
  } else {
    hasMoreMsgData.value = false;
  }
  isLoading.value = false;
};
// 会话标题
const conversationName = (conversation) => {
  if (conversation.type === 'single') {
    let chatPerson = '';
    if (conversation.personList && conversation.personList instanceof Array) {
      for (let j = 0; j < conversation.personList.length; j++) {
        const person = conversation.personList[j];
        if (person !== layout.session.user.distinguishedName) {
          chatPerson = person;
        }
      }
      if (chatPerson) {
        return formatPersonName(chatPerson);
      }
    }
  }
  return conversation.title;
};
// 点击发送消息
const clickSendMsg = () => {
  const text = inputMsg.value;
  if (text.trim() === '') {
    $OOUI.notice.warn(lp.alert, lp.noMessage);
    return;
  }
  const time = ymdhms(new Date());
  const body = {body: text, type: 'text'};
  const bodyJson = JSON.stringify(body);

  const textMessage = {
    id: `${uuid()}`,
    conversationId: conversation.value.id,
    body: bodyJson,
    createPerson: layout.session.user.distinguishedName,
    createTime: time,
    sendStatus: 1,
  };
  if (quoteMessage.value && quoteMessage.value.id) {
    textMessage.quoteMessageId = quoteMessage.value.id;
    textMessage.quoteMessage = quoteMessage.value;
  }
  // 添加到界面上
  msgList.value.push(textMessage);
  _sendTextMsg(textMessage);
  // 会话更新
  quoteMessage.value = null;
  inputMsg.value = '';
  scrollToBottom();
};
const _sendTextMsg = async (textMessage) => {
  await _sendMsgOnline(textMessage);
  eventBus.publish(EventName.refreshMyConversation, 'sendMsg');
};
const _sendMsgOnline = async (msg) => {
  const res = await imAction('msgCreate', msg);
  if (res) {
    console.log('发送消息成功', res);
  }
};
// 输入框回车事件
const inputKeyupEvent = (e) => {
  if (e.keyCode === 13) {
    e.preventDefault();
    if (e.ctrlKey === true) {
      const text = inputMsg.value;
      inputMsg.value = text + '\n';
      document.getElementById('chatMsgNode').focus();
    } else {
      clickSendMsg();
    }
  }
};
const clickSendFile = () => {
  chooseSingleFile((file) => {
    if (file) {
      _sendFileMsg(file);
    }
  });
};
/**
 * ★ 从「我的网盘」选文件发送（2026-10-15 源码级实现）
 * 旧做法是构建期往压缩后的 main.js 里插入一个 __o2DrivePickIM 全局函数 +
 * 由 Python 补丁拼 HTML 锚点；现在直接调用源码模块的 pickDrive()，
 * 选中的 File 与手动选择文件走【完全同一条】发送链路（_sendFileMsg）。
 */
const clickPickDrive = () => {
  if (!conversation.value || !conversation.value.id) {
    toast('请先打开一个聊天会话再选文件', true);
    return;
  }
  pickDrive({
    onPick: (file) => {
      if (file) {
        _sendFileMsg(file);
      }
    }
  });
};
/**
 * ★ 上传结果统一收口（对齐微信：看得见进度、看得见结果、刷新及时、不重发）
 *
 * 旧实现的缺陷（用户反馈「上传附件没有进度和完成提醒，刷新也不及时，
 * 导致上传好几次」）：上传完成后【不提示、不刷新、不在本地落位消息】，
 * 发送者完全看不出是否发成功，于是反复点击。
 */
const _handleUploadResult = (res, convId, fileName) => {
  if (!res || !res.ok) {
    if (res && res.duplicate) {
      // 重复提交不是错误，只做一次轻提示（这正是「上传好几次」要拦掉的场景）
      toast(res.error || '该文件正在上传中，请稍候…', false);
    } else {
      toast('「' + fileName + '」发送失败：' + ((res && res.error) || '未知错误'), true);
    }
    return;
  }
  // 成功：本地立即落位消息（不等 WS 回包），随后刷新会话列表（排序/摘要/未读）
  if (res.message && conversation.value && conversation.value.id === convId) {
    if (msgList.value.findIndex((e) => e.id === res.message.id) < 0) {
      msgList.value.push(res.message);
      scrollToBottom();
    }
  }
  eventBus.publish(EventName.refreshMyConversation, 'sendMsg');
  toast('「' + fileName + '」已发送');
};
const _sendFileMsg = async (file) => {
  if (!conversation.value || !conversation.value.id) {
    toast('请先打开一个聊天会话再发送文件', true);
    return;
  }
  const convId = conversation.value.id;
  const res = await uploadFileListInstance.addUploadFileAndSendMessage(file, convId);
  _handleUploadResult(res, convId, file.name);
};
// ---- 上传队列 UI 辅助 ----
const uploadPercentText = (file) => {
  if (file.status === 'done') {
    return '已完成';
  }
  if (file.status === 'error') {
    return '失败';
  }
  const p = Number(file.progress);
  return (isNaN(p) ? 0 : Math.max(0, Math.min(100, Math.round(p)))) + '%';
};
const uploadRemoveItem = (file) => {
  uploadFileListInstance.removeUploadFile(file.id);
};
const uploadRetryItem = async (file) => {
  const res = await uploadFileListInstance.retryUpload(file.id);
  _handleUploadResult(res, file.conversationId, file.name);
};
// 删除引用消息
const deleteQuoteMessage = () => {
  quoteMessage.value = null;
};
// 引用消息内容
const quoteMsgContent = (quoteMessage) => {
  if (!quoteMessage || !quoteMessage.body || !quoteMessage.createPerson) {
    console.error('错误的引用消息');
    return '';
  }
  const msgBody = JSON.parse(quoteMessage.body);
  let name = formatPersonName(quoteMessage.createPerson);
  name += ': ';
  let lastMessage = msgBody.body;
  if (msgBody.type === 'process') {
    let title = msgBody.title;
    if (!title) {
      title = '【' + msgBody.processName + '】- ' + lp.noTitle;
    }
    name +=  title;
  } else if (msgBody.type === 'cms') {
    name +=  msgBody.title || '';
  } else  if (msgBody.type !== 'emoji' && msgBody.type !== 'image') { // 表情和图片不需要再加内容，只需要 name:
    let quoteDesc = contentEscapeBackToSymbol(lastMessage);
    if (containsUrl(quoteDesc)) {
      quoteDesc = marked.parse(convertUrlToMarkdown(quoteDesc))
    }
    name += quoteDesc
    if (msgBody.type === 'file') {
      name += ' ' + msgBody.fileName;
    }
  } else {
    name += lastMessage;
  }
  return name;
};
// 选择消息
const clickSelectMsg = (msg) => {
  const i = msgSelectedList.value.findIndex((m) => m.id === msg.id);
  if (i > -1) {
    msgSelectedList.value.splice(i, 1);
  } else {
    msgSelectedList.value.push(msg);
  }
};
// 打开消息
const clickOpenMsg = (msg) => {
  if (chooseMode.value) {
    clickSelectMsg(msg);
  } else {
    // 打开消息
    if (!needClickMsg(msg)) {
      return;
    }
    eventBus.publish(EventName.openMsg, msg);
  }
};
// 引用消息
const clickOpenQuoteMsg = (msg) => {
  console.debug('open quote msg  === main', msg);
  if (!chooseMode.value) {
    eventBus.publish(EventName.openMsg, msg);
  }
};
// 选择表情
const chooseEmoji = (emoji) => {
  console.log('选择了表情', emoji);
  const text = inputMsg.value;
  inputMsg.value = text + emoji;
};
const openEmojiPicker = () => {
  showEmoji.value = true;
};
const closeEmojiPicker = () => {
  showEmoji.value = false;
};
// 右键菜单
const msgContextMenu = (msg, e) => {
  e.preventDefault();
  const menuList = []; // 菜单列表
  if (imConfigInstance.enableRevokeMsg === true) {
    const createPerson = msg.createPerson;
    const me = layout.session.user.distinguishedName;
    let revokeMinute = imConfigInstance.revokeOutMinute ?? 2;
    if (revokeMinute <= 0) {
      revokeMinute = 2;
    }
    let createTime = toDate(msg.createTime);
    if (revokeMinute > 0 && new Date().getTime() - createTime.getTime() < revokeMinute * 60 * 1000 && createPerson === me) {
      menuList.push({id: 'revokeMsg', text: lp.msgMenuItemRevokeMsg});
    }
  }
  // 转发
  menuList.push({id: 'forward', text: lp.msgMenuItemForwardMsg});
  // 收藏
  menuList.push({id: 'collection', text: lp.msgMenuItemCollectionMsg});
  // 选择
  menuList.push({id: 'select', text: lp.msgMenuItemSelectMsg});
  // 引用
  menuList.push({id: 'quote', text: lp.msgMenuItemQuoteMsg});
  console.debug('右键菜单', menuList);
  createContextMenu({
    callback: (menu) => {
      switch (menu.id) {
        case 'revokeMsg':
          _revokeMsg(msg);
          break;
        case 'forward':
          _forwardMsg(msg);
          break;
        case 'collection':
          _collectMsg(msg);
          break;
        case 'quote':
          _quoteMsg(msg);
          break;
        case 'select':
          _openChooseMode(msg);
          break;
      }
    },
    menuList: menuList,
    top: e.clientY,
    left: e.clientX,
  });
};
// 选择
const _openChooseMode = (msg) => {
  chooseMode.value = true;
  msgSelectedList.value = [msg];
  console.debug('选择模式', msg);
};
// 转发
const _forwardMsg = (msg) => {
  conversationPicker(eventBus).then((conv) => {
    if (conv) {
      console.debug('转发', msg, conv);
      _forwardMsgListOnline(conv, [msg]);
    }
  });
};
// 撤回
const _revokeMsg = (msg) => {
  console.debug('撤回', msg);
  imAction('msgRevoke', msg.id);
  msgList.value.splice(
      msgList.value.findIndex((e) => e.id === msg.id),
      1,
  );
};
// 引用
const _quoteMsg = (msg) => {
  console.debug('引用', msg);
  quoteMessage.value = msg;
};
// 收藏
const _collectMsg = (msg) => {
  console.debug('收藏', msg);
  _collectMsgListOnline([msg]);
};
const _collectMsgListOnline = async (msgList) => {
  const body = {
    msgIdList: msgList.map((e) => e.id),
  };
  const res = await imAction('msgCollectionSave', body);
  if (res) {
    console.debug('收藏成功', res);
    $OOUI.notice.success(lp.alert, lp.msgCollectionSuccess);
  }
};
// 转发消息
const _forwardMsgListOnline = async (conv, list) => {
  if (!conv || !list || list.length < 1) {
    return;
  }
  const time = ymdhms(new Date());
  for (let i = 0; i < list.length; i++) {
    let msg = list[i];
    msg.id = `${uuid()}`;
    msg.conversationId = conv.id;
    msg.createPerson = layout.session.user.distinguishedName;
    msg.createTime = time;
    await _sendMsgOnline(msg);
    if (conv.id === conversation.value.id) {
      msgList.value.push(msg);
    }
  }
  eventBus.publish(EventName.refreshMyConversation, 'sendMsg');
};
// 逐个消息转发
const clickOneByOneForward = () => {
  if (msgSelectedList.value.length < 1) {
    $OOUI.notice.warn(lp.alert, lp.msgNeedSelectMessage);
    return;
  }
  conversationPicker(eventBus).then((conv) => {
    if (conv) {
      console.debug('转发one by one', conv);
      _forwardMsgListOnline(conv, msgSelectedList.value);
      closeChooseMode();
    }
  });
};
// 合并消息转发
const clickMergeForward = () => {
  if (msgSelectedList.value.length < 1) {
    $OOUI.notice.warn(lp.alert, lp.msgNeedSelectMessage);
    return;
  }
  let list = msgSelectedList.value.slice();
  // 倒序
  list.sort(function (a, b) {
    return new Date(b.createTime) - new Date(a.createTime);
  });
  let descList;
  if (list.length > 4) {
    descList = list.slice(0, 4);
  } else {
    descList = list.slice();
  }
  let desc = '';
  for (let i = 0; i < descList.length; i++) {
    const msg = descList[i];
    let name = msg.createPerson;
    if (msg.createPerson.indexOf('@') !== -1) {
      name = name.substring(0, msg.createPerson.indexOf('@'));
    }
    const body = JSON.parse(msg.body);
    let content = body.body;
    if (body.type === 'text') {
      content = contentEscapeBackToSymbol(body.body);
    } else if (body.type === 'emoji') {
      content = lp.msgTypeEmoji;
    }
    desc += name + ': ' + content + '\n';
  }
  let title = '群聊的聊天记录';
  if (conversation.value.type === 'single') {
    title =
        conversation.value.personList
            .map((p) => {
              return formatPersonName(p);
            })
            .join(',') + '的聊天记录';
  }
  const msgbody = {
    body: lp.msgTypeHistory,
    type: 'messageHistory',
    messageHistoryTitle: title,
    messageHistoryDesc: desc,
    messageHistoryIds: list.map((e) => e.id),
  };
  const message = {
    id: '',
    conversationId: conversation.value.id,
    body: JSON.stringify(msgbody),
    createPerson: layout.session.user.distinguishedName,
    createTime: '',
    sendStatus: 1,
  };
  conversationPicker(eventBus).then((conv) => {
    if (conv) {
      console.debug('转发 merge ', conv);
      _forwardMsgListOnline(conv, [message]);
      closeChooseMode();
    }
  });
};
// 收藏消息
const clickCollectionMsg = () => {
  if (msgSelectedList.value.length < 1) {
    $OOUI.notice.warn(lp.alert, lp.msgNeedSelectMessage);
    return;
  }
  let list = msgSelectedList.value.slice();
  // 顺序
  list.sort(function (a, b) {
    return new Date(a.createTime) - new Date(b.createTime);
  });
  _collectMsgListOnline(list);
  closeChooseMode();
};
// 关闭选择模式
const closeChooseMode = () => {
  chooseMode.value = false;
  msgSelectedList.value = [];
};
// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    msgNode.value[msgList.value.length - 1].scrollIntoView();
  });
};

// 滚动事件 滚动到顶部的时候加载更多消息
const msgListScrollEvent = () => {
  //滑到顶部时触发下次数据加载
  const chatBodyNode = document.querySelector('#chatBodyNode');
  if (chatBodyNode.scrollTop === 0) {
    if (hasMoreMsgData.value) {
      // 有更多数据
      // 间隔1秒 防止频繁
      setTimeout(() => {
        //将scrollTop置为10以便下次滑到顶部
        chatBodyNode.scrollTop = 10;
        //加载数据
        loadMoreMsgData();
      }, 300);
    }
  }
};

const showImChat = () => {
  if (windowStateInstance.isMobile) {
    if (conversation.value && conversation.value.id) {
      return !showChatInfo.value
    } else {
      return false
    }
  } else {
    return (conversation.value && conversation.value.id)
  }
}
</script>

<template>
  <div class="im-chat-row">
    <div class="im-chat" v-if=" showImChat() ">
      <!-- 进度条：上传中 / 已完成 / 失败 三态可视化（对齐微信的「看得见进度与结果」） -->
      <div class="im-chat-progress" v-if="uploadFileListInstance.uploadFileList.length > 0">
        <div v-for="file in uploadFileListInstance.uploadFileList" :key="file.id"
             class="im-upload-item" :class="'im-upload-' + (file.status || 'uploading')">
          <div class="im-upload-icon">
            <i :class="file.status === 'error'
                        ? 'ooicon-error'
                        : (file.status === 'done' ? 'ooicon-checkmark' : 'ooicon-upload')"></i>
          </div>
          <div class="im-upload-main">
            <div class="im-upload-line">
              <span class="im-upload-name" :title="file.name">{{ file.name }}</span>
              <span class="im-upload-percent">{{ uploadPercentText(file) }}</span>
            </div>
            <div class="im-upload-track">
              <div class="im-upload-bar" :style=" `width: ${file.progress}%;` "></div>
            </div>
            <div class="im-upload-tip" v-if="file.status === 'error'">{{ file.error || '上传失败' }}</div>
          </div>
          <div class="im-upload-actions">
            <span v-if="file.status === 'error'" class="im-upload-act" @click="uploadRetryItem(file)">重试</span>
            <span class="im-upload-act" @click="uploadRemoveItem(file)">
              {{ file.status === 'uploading' ? '取消' : '移除' }}
            </span>
          </div>
        </div>
      </div>
      <div class="im-chat-header" v-if="!hideSide">
        <div class="im-chat-header-left">
          <div class="im-chat-header-menu" v-if="windowStateInstance.isMobile" @click="closeMainPage">
            <i class="ooicon-process-goback icon"></i>
          </div>
        </div>
        <div class="im-chat-header-center">
          {{ conversationName(conversation) }}
        </div>
        <div class="im-chat-header-right">
          <div class="im-chat-header-menu" @click="showChatInfo = true">
            <i class="ooicon-point3 icon"></i>
          </div>
        </div>
      </div>

      <div class="im-chat-body" id="chatBodyNode" ref="chatBodyNodeRef" @scroll="msgListScrollEvent">
        <div class="chat-no-more-data" v-if="!hasMoreMsgData">
          {{ lp.msgLoadNoMoreData }}
        </div>
        <div v-for="msg in msgList" :key="msg.id" ref="msgNode">
          <div class="im-chat-msg-body">
            <div class="im-chat-msg-select" v-if="chooseMode" @click="clickSelectMsg(msg)">
              <i
                  :class="
                                    msgSelectedList.findIndex((m) => m.id === msg.id) > -1
                                        ? 'ooicon-checkbox-checked mainColor_color icon'
                                        : 'ooicon-checkbox-unchecked icon'
                                "
              ></i>
            </div>
            <div class="im-chat-msg-body-content" @contextmenu="msgContextMenu(msg, $event)">
              <ChatMsg :msg="msg" @clickOpenQuoteMsg="clickOpenQuoteMsg" @clickOpenMsg="clickOpenMsg"></ChatMsg>
            </div>
          </div>
        </div>
      </div>

      <div class="im-chat-footer">
        <div class="im-chat-footer-choose" v-if="chooseMode">
          <div class="flex-3">
            <oo-button :oo-title="lp.chatChooseModeOneByOneForward" @click="clickOneByOneForward">
              {{ lp.chatChooseModeOneByOneForward }}
            </oo-button>
            <oo-button :oo-title="lp.chatChooseModeMergeForward" @click="clickMergeForward">
              {{ lp.chatChooseModeMergeForward }}
            </oo-button>
            <oo-button :oo-title="lp.chatChooseModeCollection" @click="clickCollectionMsg">
              {{ lp.chatChooseModeCollection }}
            </oo-button>
          </div>
          <div class="flex-1">
            <oo-button :oo-title="lp.cancel" type="cancel" @click="closeChooseMode">{{ lp.cancel }}</oo-button>
          </div>
        </div>
        <div class="im-chat-footer-input" v-else>
          <div class="im-chat-footer-input-tool">
            <div class="icon-btn" @click="openEmojiPicker">
              <i class="ooicon-emote icon"></i>
            </div>
            <div class="icon-btn" @click="clickSendFile">
              <i class="ooicon-folder-open icon"></i>
            </div>
            <!-- ★ 网盘取件：从「我的网盘」选文件发送（与手动选择文件同一条发送链路） -->
            <div class="icon-btn" title="从我的网盘选择文件" @click="clickPickDrive">
              <i class="ooicon-drive icon"></i>
            </div>
          </div>
          <div class="im-chat-footer-input-text">
            <textarea id="chatMsgNode" v-model="inputMsg" :placeholder="lp.enterMessage"
                      @keydown="inputKeyupEvent"></textarea>
          </div>
          <div class="im-chat-footer-input-bottom">
            <div class="quote-msg">
              <div class="im-chat-quote-message-box" v-if="quoteMessage">
                <div class="im-chat-quote-message-desc" ref="quoteDescRef" v-html="quoteMsgContent(quoteMessage)"></div>
                <div class="im-icon-btn" @click="deleteQuoteMessage">
                  <i class="ooicon-close icon"></i>
                </div>
              </div>
            </div>
            <div class="key-tips">{{ lp.sendKeyTips }}</div>
            <div class="send-btn" @click="clickSendMsg">
              <!--            <oo-button :oo-title="lp.send" @click="clickSendMsg">{{ lp.send }}</oo-button>-->
              <i class="ooicon-send icon"></i>
            </div>
          </div>
        </div>
      </div>
      <!--    emoji 选择 -->
      <EmojiPicker v-if="showEmoji" @chooseEmoji="chooseEmoji" @closeEmojiPicker="closeEmojiPicker"></EmojiPicker>
    </div>
    <!--  聊天信息 -->
    <ChatInfo v-if="showChatInfo && conversation" :conversation="conversation"
              @closeChatInfo="showChatInfo = false"></ChatInfo>
  </div>
</template>

<style scoped></style>
