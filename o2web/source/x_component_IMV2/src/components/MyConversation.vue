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
const addConversationToListEventFun = (data) => {
  console.debug("addConversationToList")
  if (data) {
    const index = myConversationList.value.findIndex((item) => item.id === data.id)
    if (index < 0) { // 会话不存在 添加
      myConversationList.value.unshift(data)
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
  const list = await imAction('myConversationList')
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
    myConversationList.value = list
    if (!chooseMode) {
      // 被踢出群之类的特殊情况
      if (isCheckNull && currentConversation.value && list.findIndex(item => item.id === currentConversation.value.id) < 0) {
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