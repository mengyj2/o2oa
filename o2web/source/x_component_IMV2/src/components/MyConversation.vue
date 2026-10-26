<script setup>
import {ref, onMounted, onUnmounted, inject,} from 'vue'
import {lp} from '@o2oa/component'
import {imAction, conversationIconUrl} from "../utils/actions.js"
import {formatPersonName, friendlyTime, toDate} from "../utils/common.js";
import {EventName} from "../utils/eventBus.js";
import {imGlobalOptions} from "../store.js";

const emit = defineEmits(["closeChooseConversation", "showContact"]);
const {openConversation} = inject('im-app')
// eventBus
const eventBus = inject('eventBus')

const imGlobalOptionsInstance = imGlobalOptions();

onMounted(() => {
  console.debug('myConversation mounted', eventBus)
  loadMyConversation()
  if (!chooseMode) {
    eventBus.subscribe(EventName.initOpenedConversation, initOpenedConversationEventFun)
    eventBus.subscribe(EventName.refreshMyConversation, refreshMyConversationEventFun)
    eventBus.subscribe(EventName.addConversationToList, addConversationToListEventFun)
    // ★ 本地乐观清零（打开会话即刻生效，不等后端回包）
    eventBus.subscribe(EventName.conversationReadLocal, conversationReadLocalEventFun)
  }
})
onUnmounted(() => {
  console.debug('myConversation unmounted', eventBus)
  if (!chooseMode) {
    eventBus.unsubscribe(EventName.initOpenedConversation)
    eventBus.unsubscribe(EventName.refreshMyConversation)
    eventBus.unsubscribe(EventName.addConversationToList)
    eventBus.unsubscribe(EventName.conversationReadLocal)
  }
})

const initOpenedConversationEventFun = (conv) => {
  console.debug("initOpenedConversation", conv)
  if (conv) {
    clickConversation(conv)
  }
}
const refreshMyConversationEventFun = (reason) => {
  console.debug("refreshMyConversation", reason)
  loadMyConversation(true, reason)
}
/**
 * ★ 本地乐观清零（2026-10-15 源码级，根治「消息全读了，未读标记刷新不及时」）
 *
 * 背景：未读角标数来自后端 /jaxrs/im/conversation/list/my 的 unreadNumber，
 *   unreadNumber 又由 IMConversationExt.lastReadTime 算出。官方前端【从不调用】
 *   PUT /jaxrs/im/conversation/{id}/read（ActionConversationRead），所以它只增不减。
 *   App.vue 现在负责上报该接口，并在上报【之前】先发本事件 ⇒ 角标零等待消失。
 * 本处理：命中会话立即置 0，并记时间戳用于「读后防抖」（见 loadMyConversation）。
 */
const _localReadAt = {}
const conversationReadLocalEventFun = (conversationId) => {
  if (!conversationId) {
    return
  }
  _localReadAt[conversationId] = Date.now()
  const item = myConversationList.value.find((m) => m.id === conversationId)
  if (item) {
    item.unreadNumber = 0
  }
}
/**
 * ★ 本地新建、后端尚未收录的会话 id（2026-10-26 源码级修复）
 *
 * 后端源码实证（x_message_assemble_communicate / ActionMyConversationList.java:62-74）：
 *   `// 单聊没有聊天消息就不展现` → `return (woMsg != null)`
 *   判据是**有没有 IMMsg 消息记录**，不是 lastMessageTime 字段（改时间字段无效）。
 *   ⇒ 新建单聊后、发出第一条消息之前，/conversation/list/my 永远不会返回它。
 *
 * 而本组件 loadMyConversation() 原本是 `myConversationList.value = list` **整体覆盖**：
 *   ① 新建会话被 unshift 进来后，任意一次刷新（WS 新消息／已读去抖）就把它冲掉；
 *   ② 紧随其后的"被踢出群"判定把「当前会话不在返回里」当成被踢，
 *      直接 currentConversation=null + openConversation(null) ⇒ 右侧对话被强制关闭。
 * 现象：点「创建聊天」像没反应，于是反复点。2026-10-26 报障当日日志实证：
 *   14:31:39~14:35:53 共 10 次 POST /jaxrs/im/conversation 全部 200，
 *   且每次之后都 read 同一个会话 b3b5b12e —— 会话确实建出来了，是被冲掉了。
 *
 * 修法：本次页面会话内记住这些 id，刷新时补回列表顶部并阻止"被踢"误判；
 *   一旦该会话出现在后端返回里（已发过消息）立即移出集合，回归官方语义；
 *   刷新页面集合即清空，不会让空会话永久堆积（保留官方"无消息不展示"的设计）。
 */
const _localNewConvIds = new Set()

const addConversationToListEventFun = (data) => {
  console.debug("addConversationToList")
  if (data) {
    const index = myConversationList.value.findIndex((item) => item.id === data.id)
    if (index < 0) { // 会话不存在 添加
      myConversationList.value.unshift(data)
    }
    if (data.id) { // ★ 标记为"本地新建"，避免下一次刷新被后端结果冲掉
      _localNewConvIds.add(data.id)
    }
    currentConversation.value = data
  }
}

// ref
const {chooseMode} = defineProps(['chooseMode']) // 选择模式
const myConversationList = ref([])
const currentConversation = ref(null)
const searchContent = ref('')
const searchMode = ref(false)
const searchConversationResultList = ref([])


// function

const loadMyConversation = async (isCheckNull, reason) => {
  let list = await imAction('myConversationList')
  if (list) {
    /**
     * ★ 读后防抖：reason === 'read' 说明本次刷新是「刚刚标记已读」触发的。
     *   若后端此时尚未把 lastReadTime 回写完（时序竞态），直接把服务端值铺回去
     *   会让刚清零的角标「闪一下又出现」。窗口内以本地记录为准强制置 0。
     *   非 'read' 刷新（如 WS 新消息）一律信服务端 —— 新消息必须照常显示未读。
     */
    if (reason === 'read') {
      const now = Date.now()
      list.forEach((item) => {
        if (item && item.id && _localReadAt[item.id] && (now - _localReadAt[item.id]) < 5000) {
          item.unreadNumber = 0
        }
      })
    }
    /**
     * ★ 保留"本地新建、后端尚未收录"的会话（2026-10-26，详见 _localNewConvIds 注释）。
     *   - 已出现在后端返回里 ⇒ 说明发过消息了，移出集合，回归官方语义；
     *   - 仍不在返回里     ⇒ 补回列表顶部，避免整体覆盖把它冲掉。
     */
    if (_localNewConvIds.size) {
      const returnedIds = new Set(list.map((item) => item.id))
      _localNewConvIds.forEach((id) => {
        if (returnedIds.has(id)) {
          _localNewConvIds.delete(id)
        }
      })
      const keepLocal = myConversationList.value.filter(
        (item) => item && _localNewConvIds.has(item.id) && !returnedIds.has(item.id)
      )
      if (keepLocal.length) {
        list = keepLocal.concat(list)
      }
    }
    myConversationList.value = list
    if (!chooseMode) {
      // 被踢出群之类的特殊情况（本地新建的空单聊不在后端返回里属正常，不算被踢）
      if (isCheckNull && currentConversation.value
        && !_localNewConvIds.has(currentConversation.value.id)
        && list.findIndex(item => item.id === currentConversation.value.id) < 0) {
        currentConversation.value = null
        openConversation(null)
      }
      // 第一次打开？ 默认选中
      // else if (currentConversation.value == null && list.length > 0) {
      //
      //   currentConversation.value = list[0]
      //   openConversation(list[0])
      // }
      if (imGlobalOptionsInstance.firstOpenConversation && list.length <= 0) {
        emit('showContact')
        imGlobalOptionsInstance.loadedConversation()
      }
    }
  }
}

/**
 * 未读角标文案：0/负值/空 ⇒ 空串（模板据此隐藏），>99 ⇒ "99+"。
 * 口径直接取后端 unreadNumber（1 条=1、2 条=2），不做前端自算，避免与后端不一致。
 */
const unreadText = (n) => {
  const v = Number(n) || 0
  if (v <= 0) {
    return ''
  }
  return v > 99 ? '99+' : String(v)
}

const inputSearch = (e) => {
  searchContent.value = e.target.value
  _searchConversation(e.target.value)
}

const _searchConversation = (content) => {
  if (!content) {
    clearSearch()
    return
  }
  const list = myConversationList.value
  searchMode.value = true
  searchConversationResultList.value = list.filter((item) => item.title.includes(content) || item.personList.filter((p) => p.includes(content)).length > 0)
}
const clearSearch = () => {
  searchContent.value = ''
  searchMode.value = false
  searchConversationResultList.value = []
}

const conversationName = (conversation) => {
  if (conversation.type === "single") {
    let chatPerson = "";
    if (conversation.personList && conversation.personList instanceof Array) {
      for (let j = 0; j < conversation.personList.length; j++) {
        const person = conversation.personList[j];
        if (person !== layout.session.user.distinguishedName) {
          chatPerson = person;
        }
      }
      if (chatPerson) {
        return formatPersonName(chatPerson)
      }
    }
  }
  return conversation.title
}
const conversationLastMessageTime = (conversation) => {
  if (conversation.lastMessage && conversation.lastMessage.createTime) {
    return friendlyTime(toDate(conversation.lastMessage.createTime));
  }
  return ''
}
const conversationLastMessage = (conversation) => {
  if (conversation.lastMessage && conversation.lastMessage.body) {
    const mBody = JSON.parse(conversation.lastMessage.body);
    let lastMessage = mBody.body;
    // if (conversation.lastMessage.createTime) {
    //   var time = this.main._friendlyTime(o2.common.toDate(this.data.lastMessage.createTime));
    //   convData.time = time;
    // }
    if (mBody.type) {
      // convData.lastMessageType = mBody.type;
      if (mBody.type === "process") {
        let title = mBody.title;
        if (!title) {
          title = "【" + mBody.processName + "】- " + lp.noTitle;
        }
        lastMessage = title;
      } else if (mBody.type === "cms") {
        lastMessage = mBody.title || "";
      }
    }
    return lastMessage
  }
  return ''
}
const clickConversation = (conversation) => {
  if (searchMode.value) {
    clearSearch()
  }
  if (chooseMode) {
    emit('closeChooseConversation', conversation)
  } else {
    currentConversation.value = conversation
    // eventBus.publish(EventName.openConversation, conversation)
    openConversation(conversation)
  }

}
</script>

<template>
  <div class="im-conversation-view">
    <div class="im-conversation-search">
      <oo-input style="flex: 1;" type="text" leftIcon="search" :value="searchContent"
                :placeholder="lp.conversationSearchPlaceholder"
                @input="inputSearch">
        <span v-if="searchContent!==''" class="arrow" slot="after-inner-after" @click="clearSearch"><i class="ooicon-error"></i></span>
      </oo-input>
    </div>
    <!--      会话列表 -->
    <div class="im-conversation-list" v-if=" !searchMode ">
      <div v-for="item in myConversationList" :key="item.id"
           :class=" item.id === currentConversation?.id ? 'im-conv-item active': 'im-conv-item' "
           @click="clickConversation(item)">
        <div class="avatar">
          <img :src="conversationIconUrl(item.id)" alt="avatar">
        </div>
        <div class="body">
          <div class="body-line">
            <div class="title"> {{ conversationName(item) }}</div>
            <div class="time">{{ conversationLastMessageTime(item) }}</div>
          </div>
          <div class="body-line margin-top-10">
            <div class="msg">
              {{ conversationLastMessage(item) }}
            </div>
            <!-- ★ 未读红数字（对话人/群名下方，数值取后端 unreadNumber；为 0 时整块不渲染） -->
            <span v-if="unreadText(item.unreadNumber) !== ''"
                  class="im-conv-unread">{{ unreadText(item.unreadNumber) }}</span>
          </div>
        </div>
      </div>
    </div>
    <!--      搜索结果 -->
    <div class="im-conversation-list" v-if=" searchMode ">
      <div v-for="item in searchConversationResultList" :key="item.id"
           :class=" item.id === currentConversation?.id ? 'im-conv-item active': 'im-conv-item' "
           @click="clickConversation(item)">
        <div class="avatar">
          <img :src="conversationIconUrl(item.id)" alt="avatar">
        </div>
        <div class="body">
          <div class="body-line">
            <div class="title"> {{ conversationName(item) }}</div>
            <div class="time">{{ conversationLastMessageTime(item) }}</div>
          </div>
          <div class="body-line margin-top-10">
            <div class="msg">
              {{ conversationLastMessage(item) }}
            </div>
            <!-- ★ 未读红数字（对话人/群名下方，数值取后端 unreadNumber；为 0 时整块不渲染） -->
            <span v-if="unreadText(item.unreadNumber) !== ''"
                  class="im-conv-unread">{{ unreadText(item.unreadNumber) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>

</template>

<style scoped>
.arrow {
  width: 2rem;
  text-align: center;
}
</style>