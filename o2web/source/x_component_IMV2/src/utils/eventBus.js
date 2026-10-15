class EventBus {

    // // 外部调用此函数实例化
    // static getInstance() {
    //   if (!EventBus.instance) {
    //     EventBus.instance = new EventBus()
    //   }
    //   return EventBus.instance
    // }

    constructor() {
        this.listeners = {};
    }

    subscribe(eventName, callback) {
        this.listeners[eventName] = callback;
    }

    unsubscribe(eventName, callback) {
        this.listeners[eventName] = null;
    }

    publish(eventName, data) {
        console.debug(' publish ', eventName, data, this.listeners)
        if (this.listeners[eventName]) {
            this.listeners[eventName](data);
        }
    }
}

export const eventBus = () => {
    return  new EventBus()
}


export class EventName {
    static addConversationToList = 'addConversationToList'
    static refreshMyConversation = 'refreshMyConversation'
    static initOpenedConversation = 'initOpenedConversation'
    static openConversation = 'openConversation'
    static updateOrDeleteConversation = 'updateOrDeleteConversation'
    static openChooseConversation = 'openChooseConversation'
    static openMsg = 'openMsg'
    static changeIMConfig = 'changeIMConfig'
    static wsAddMsg = 'wsAddMsg'
    static wsRevokeMsg = 'wsRevokeMsg'
    // ★ 2026-10-15 源码级：本地乐观清零点（打开会话/收到当前会话新消息即刻清零未读）
    static conversationReadLocal = 'conversationReadLocal'
    // ★ 2026-10-15 源码级：服务端刷新后的会话列表事件，携带最新会话数组
    static conversationUnread = 'conversationUnread'
}
