Ant =  {};
Ant.Wiget = new Class({

    Implements: [Options, Events],
    options : {
    },
    initialize : function( options ){
        this.setOptions( options || {});
    },
    notice:function(title,contentNode,duration,onClose,type,placement){

        if(!window.noticePlacementNode){
            noticePlacementNode = new Element("div",{"class":"ant-notification ant-notification-topRight"}).inject(this.contentNode.getElements('body')[0]);
        }

        var noticeNode = new Element("div",{"class":"ant-notification-notice ant-notification-notice-closable"}).inject(noticePlacementNode);
        var noticeContentNode = new Element("div",{"class":"ant-notification-notice-content"}).inject(noticeNode);
        var noticeTypeNode = new Element("div",{"class":"ant-notification-notice-with-icon"}).inject(noticeContentNode);
        var noticeTypeIconNode = new Element("i",{"class":"anticon anticon-info-circle-o ant-notification-notice-icon ant-notification-notice-icon-info"}).inject(noticeTypeNode);

        switch (type) {
            case 'success':
                noticeTypeIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="check-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M699 353h-46.9c-10.2 0-19.9 4.9-25.9 13.3L469 584.3l-71.2-98.8c-6-8.3-15.6-13.3-25.9-13.3H325c-6.5 0-10.3 7.4-6.5 12.7l124.6 172.8a31.8 31.8 0 0 0 51.7 0l210.6-292c3.9-5.3.1-12.7-6.4-12.7z"></path><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"></path></svg>');
                break;
            case 'error':
                noticeTypeIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="close-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M685.4 354.8c0-4.4-3.6-8-8-8l-66 .3L512 465.6l-99.3-118.4-66.1-.3c-4.4 0-8 3.5-8 8 0 1.9.7 3.7 1.9 5.2l130.1 155L340.5 670a8.32 8.32 0 0 0-1.9 5.2c0 4.4 3.6 8 8 8l66.1-.3L512 564.4l99.3 118.4 66 .3c4.4 0 8-3.5 8-8 0-1.9-.7-3.7-1.9-5.2L553.5 515l130.1-155c1.2-1.4 1.8-3.3 1.8-5.2z"></path><path d="M512 65C264.6 65 64 265.6 64 513s200.6 448 448 448 448-200.6 448-448S759.4 65 512 65zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"></path></svg>');
                break;
            case 'warn':
                noticeTypeIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="exclamation-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"></path><path d="M464 688a48 48 0 1 0 96 0 48 48 0 1 0-96 0zm24-112h48c4.4 0 8-3.6 8-8V296c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v272c0 4.4 3.6 8 8 8z"></path></svg>');
                break;
            case 'info':
                noticeTypeIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="info-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"></path><path d="M464 336a48 48 0 1 0 96 0 48 48 0 1 0-96 0zm72 112h-48c-4.4 0-8 3.6-8 8v272c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8V456c0-4.4-3.6-8-8-8z"></path></svg>');
                break;
            default:
                noticeTypeIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="info-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"></path><path d="M464 336a48 48 0 1 0 96 0 48 48 0 1 0-96 0zm72 112h-48c-4.4 0-8 3.6-8 8v272c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8V456c0-4.4-3.6-8-8-8z"></path></svg>');
        }
        var noticeTitleNode = new Element("div",{"class":"ant-notification-notice-message"}).inject(noticeTypeNode);
        noticeTitleNode.set("text",title);

        var noticeDescriptionNode = new Element("div",{"class":"ant-notification-notice-description"}).inject(noticeTypeNode);
        noticeDescriptionNode.set("text",contentNode);

        var noticeCloseNode = new Element("div",{"class":"ant-notification-notice-close"}).inject(noticeNode);
        var noticeContentIconNode = new Element("i",{"class":"anticon anticon-close ant-notification-close-icon"}).inject(noticeCloseNode);
        noticeContentIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="close" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M563.8 512l262.5-312.9c4.4-5.2.7-13.1-6.1-13.1h-79.8c-4.7 0-9.2 2.1-12.3 5.7L511.6 449.8 295.1 191.7c-3-3.6-7.5-5.7-12.3-5.7H203c-6.8 0-10.5 7.9-6.1 13.1L459.4 512 196.9 824.9A7.95 7.95 0 0 0 203 838h79.8c4.7 0 9.2-2.1 12.3-5.7l216.5-258.1 216.5 258.1c3 3.6 7.5 5.7 12.3 5.7h79.8c6.8 0 10.5-7.9 6.1-13.1L563.8 512z"></path></svg>');

        switch(placement){
            case 'topLeft':
                noticePlacementNode.setStyles({
                    "left": "0px",
                    "top": "24px",
                    "bottom": "auto"
                });
                break;
            case 'topRight':
                noticePlacementNode.setStyles({
                    "right": "0px",
                    "top": "24px",
                    "bottom": "auto"
                });
                break;
            case 'bottomLeft':
                noticePlacementNode.setStyles({
                    "left": "0px",
                    "top": "auto",
                    "bottom": "24px"
                });
                break;
            case 'bottomRight':
                noticePlacementNode.setStyles({
                    "right": "0px",
                    "top": "auto",
                    "bottom": "24px"
                });
                break;
            default:
                noticePlacementNode.setStyles({
                    "right": "0px",
                    "top": "24px",
                    "bottom": "auto"
                });
        }

        noticeCloseNode.addEvent("click",function(){
            noticeNode.destroy();
            if(onClose) onClose();
        });

        if(duration){
            (function(){
                noticeNode.destroy();
                if(onClose) onClose();
            }).delay(duration);
        }

    },
    modal:function(title,contentNode,footerNode,styles,onClose){
        var modalContainerNode = new Element("div").inject(document.body);
        var modalMaskNode = new Element("div",{"class":"ant-modal-mask"}).inject(modalContainerNode);
        var modalWrapNode = new Element("div",{"class":"ant-modal-wrap"}).inject(modalContainerNode);

        var modalNode = new Element("div",{"class":"ant-modal"}).inject(modalWrapNode);
        if(styles){
            if(styles.width) modalNode.setStyle("width",styles.width);
            if(styles.height) contentNode.setStyle("height",styles.height);
        }else{
            modalNode.setStyle("width",520);
        }

        var modalContentNode = new Element("div",{"class":"ant-modal-content"}).inject(modalNode);

        var modalCloseNode = new Element("button",{"class":"ant-modal-close"}).inject(modalContentNode);
        var modalCloseXNode = new Element("span",{"class":"ant-modal-close-x"}).inject(modalCloseNode);
        var modalCloseIconNode = new Element("i",{"class":"anticon anticon-close ant-modal-close-icon"}).inject(modalCloseXNode);
        modalCloseIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="close" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M563.8 512l262.5-312.9c4.4-5.2.7-13.1-6.1-13.1h-79.8c-4.7 0-9.2 2.1-12.3 5.7L511.6 449.8 295.1 191.7c-3-3.6-7.5-5.7-12.3-5.7H203c-6.8 0-10.5 7.9-6.1 13.1L459.4 512 196.9 824.9A7.95 7.95 0 0 0 203 838h79.8c4.7 0 9.2-2.1 12.3-5.7l216.5-258.1 216.5 258.1c3 3.6 7.5 5.7 12.3 5.7h79.8c6.8 0 10.5-7.9 6.1-13.1L563.8 512z"></path></svg>');

        // modalWrapNode.addEvent("click",function(ev){
        //     if(!ev.target.getParent(".ant-modal-content")){
        //         if(onClose) onClose();
        //         modalContainerNode.destroy();
        //     }
        // });

        modalCloseNode.addEvent("click",function(){
            if(onClose) onClose();
            modalContainerNode.destroy();
        });
        if(title){
            var modalHeaderNode  = new Element("div",{"class":"ant-modal-header"}).inject(modalContentNode);
            var modalTitleNode = new Element("div",{"class":"ant-modal-title"}).inject(modalHeaderNode);
            modalTitleNode.set("text",title);
        }
        var modalBodyNode  = new Element("div",{"class":"ant-modal-body"}).inject(modalContentNode);

        contentNode.inject(modalBodyNode);

        if(footerNode){
            var modalFooterNode  = new Element("div",{"class":"ant-modal-footer"}).inject(modalContentNode);

            footerNode.inject(modalFooterNode);
        }
        return modalContainerNode;
    },
    message:function(type,content,duration,onClose){
        if(!window.messageNode){
            messageNode = new Element("div",{
                "class":"ant-message"
            }).inject(document.body);
        }

        var messageContainerNode = new Element("div",{"class":"ant-message-notice"}).inject(messageNode);
        var messageContentNode = new Element("div",{
            "class":"ant-message-notice-content"
        }).inject(messageContainerNode);

        var messageCustomContentNode = new Element("div",{
            "class":"ant-message-custom-content ant-message-success"
        }).inject(messageContentNode);

        var messageCustomIconNode = new Element("i",{
            "class":"anticon anticon-check-circle"
        }).inject(messageCustomContentNode);

        switch (type) {
            case 'success':
                messageCustomIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="check-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm193.5 301.7l-210.6 292a31.8 31.8 0 0 1-51.7 0L318.5 484.9c-3.8-5.3 0-12.7 6.5-12.7h46.9c10.2 0 19.9 4.9 25.9 13.3l71.2 98.8 157.2-218c6-8.3 15.6-13.3 25.9-13.3H699c6.5 0 10.3 7.4 6.5 12.7z"></path></svg>');
                break;
            case 'info':
                messageCustomIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="info-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm32 664c0 4.4-3.6 8-8 8h-48c-4.4 0-8-3.6-8-8V456c0-4.4 3.6-8 8-8h48c4.4 0 8 3.6 8 8v272zm-32-344a48.01 48.01 0 0 1 0-96 48.01 48.01 0 0 1 0 96z"></path></svg>');
                break;
            case 'error':
                messageCustomIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="close-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm165.4 618.2l-66-.3L512 563.4l-99.3 118.4-66.1.3c-4.4 0-8-3.5-8-8 0-1.9.7-3.7 1.9-5.2l130.1-155L340.5 359a8.32 8.32 0 0 1-1.9-5.2c0-4.4 3.6-8 8-8l66.1.3L512 464.6l99.3-118.4 66-.3c4.4 0 8 3.5 8 8 0 1.9-.7 3.7-1.9 5.2L553.5 514l130 155c1.2 1.5 1.9 3.3 1.9 5.2 0 4.4-3.6 8-8 8z"></path></svg>');
                break;
            case 'warn':
                messageCustomIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="exclamation-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm-32 232c0-4.4 3.6-8 8-8h48c4.4 0 8 3.6 8 8v272c0 4.4-3.6 8-8 8h-48c-4.4 0-8-3.6-8-8V296zm32 440a48.01 48.01 0 0 1 0-96 48.01 48.01 0 0 1 0 96z"></path></svg>');
                break;
            case 'loading':
                messageCustomIconNode.set("html",'<svg viewBox="0 0 1024 1024" focusable="false" class="anticon-spin" data-icon="loading" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M988 548c-19.9 0-36-16.1-36-36 0-59.4-11.6-117-34.6-171.3a440.45 440.45 0 0 0-94.3-139.9 437.71 437.71 0 0 0-139.9-94.3C629 83.6 571.4 72 512 72c-19.9 0-36-16.1-36-36s16.1-36 36-36c69.1 0 136.2 13.5 199.3 40.3C772.3 66 827 103 874 150c47 47 83.9 101.8 109.7 162.7 26.7 63.1 40.2 130.2 40.2 199.3.1 19.9-16 36-35.9 36z"></path></svg>');
                break;
            default:
                messageCustomIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="info-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm32 664c0 4.4-3.6 8-8 8h-48c-4.4 0-8-3.6-8-8V456c0-4.4 3.6-8 8-8h48c4.4 0 8 3.6 8 8v272zm-32-344a48.01 48.01 0 0 1 0-96 48.01 48.01 0 0 1 0 96z"></path></svg>');
        }

        var messageCustomTitleNode = new Element("span",{
            "text":content
        }).inject(messageCustomContentNode);

        (function(){
            messageContainerNode.destroy();
            if(onClose) onClose();
        }).delay(duration?duration:2000);

    },
    popOver : function(ev,title,content,placement){
        if(!placement) placement = "top";

        var popoverNode = new Element("div",{"class":"ant-popover ant-popover-placement-" + placement}).inject(this.contentNode.getElements('body')[0]);

        var popoverContentNode = new Element("div",{"class":"ant-popover-content"}).inject(popoverNode);
        var popoverArrowNode = new Element("div",{"class":"ant-popover-arrow"}).inject(popoverContentNode);
        var popoverInnerNode = new Element("div",{"class":"ant-popover-inner"}).inject(popoverContentNode);

        var popoverInnerTitleNode = new Element("div",{"class":"ant-popover-title"}).inject(popoverInnerNode);
        popoverInnerTitleNode.set("html",title);

        var popoverInnerContentNode = new Element("div",{"class":"ant-popover-inner-content"}).inject(popoverInnerNode);
        popoverInnerContentNode.set("html",content);

        var position = ev.target.getPosition();
        var size = popoverNode.getSize();
        var left,top;
        switch (placement) {
            case 'leftTop':
                left = position.x -  (size.x);
                top = position.y;
                break;
            case 'top':
                left = position.x -  (size.x)/2 + (ev.target.getSize().x)/2;
                top = position.y - size.y;
                break;
            case 'rightTop':
                left = position.x + ev.target.getSize().x;
                top = position.y;
                break;
            case 'bottom' :
                left = position.x;
                top = position.y + ev.target.getSize().y;
                break;
            default:
                left = position.x -  (size.x)/2 + (ev.target.getSize().x)/2;
                top = position.y - size.y;
                break;
        }
        popoverNode.setStyles({
            "left": left,
            "top": top
        })

        ev.target.addEvent("mouseleave",function(){
            popoverNode.destroy();
        });

    },
    confirm : function(title,contentNode,styles,onOk,onCancel){

        var modalContainerNode = new Element("div").inject(document.body);
        var modalMaskNode = new Element("div",{"class":"ant-modal-mask"}).inject(modalContainerNode);
        var modalWrapNode = new Element("div",{"class":"ant-modal-wrap"}).inject(modalContainerNode);

        var modalNode = new Element("div",{"class":"ant-modal"}).inject(modalWrapNode);
        if(styles){
            if(styles.width) modalNode.setStyle("width",styles.width);
            if(styles.height) contentNode.setStyle("height",styles.height);
        }else{
            modalNode.setStyle("width",520);
        }

        var modalContentNode = new Element("div",{"class":"ant-modal-content"}).inject(modalNode);

        var modalCloseNode = new Element("button",{"class":"ant-modal-close"}).inject(modalContentNode);
        var modalCloseXNode = new Element("span",{"class":"ant-modal-close-x"}).inject(modalCloseNode);
        var modalCloseIconNode = new Element("i",{"class":"anticon anticon-close ant-modal-close-icon"}).inject(modalCloseXNode);
        modalCloseIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="close" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M563.8 512l262.5-312.9c4.4-5.2.7-13.1-6.1-13.1h-79.8c-4.7 0-9.2 2.1-12.3 5.7L511.6 449.8 295.1 191.7c-3-3.6-7.5-5.7-12.3-5.7H203c-6.8 0-10.5 7.9-6.1 13.1L459.4 512 196.9 824.9A7.95 7.95 0 0 0 203 838h79.8c4.7 0 9.2-2.1 12.3-5.7l216.5-258.1 216.5 258.1c3 3.6 7.5 5.7 12.3 5.7h79.8c6.8 0 10.5-7.9 6.1-13.1L563.8 512z"></path></svg>');

        modalCloseNode.addEvent("click",function(){
            modalContainerNode.destroy();
        });
        var modalHeaderNode  = new Element("div",{"class":"ant-modal-header"}).inject(modalContentNode);
        var modalTitleNode = new Element("div",{"class":"ant-modal-title"}).inject(modalHeaderNode);
        modalTitleNode.set("text",title);

        var modalBodyNode  = new Element("div",{"class":"ant-modal-body"}).inject(modalContentNode);

        if(typeof(contentNode)==="string"){
            contentNode = new Element('div',{'text':contentNode});
        }
        contentNode.inject(modalBodyNode);

        var modalFooterNode  = new Element("div",{"class":"ant-modal-footer"}).inject(modalContentNode);
        var footerButtonListNode = new Element("div").inject(modalFooterNode);

        var okButtonNode = new Element("button",{"class":"ant-btn ant-btn-primary"}).inject(footerButtonListNode);
        okButtonNode.set("html",'<span>确 定</span');
        okButtonNode.addEvent("click",function(){
            if(onOk){
                onOk();
            }
            modalContainerNode.destroy();
        });
        var cancelButtonNode = new Element("button",{"class":"ant-btn"}).inject(footerButtonListNode);
        cancelButtonNode.set("html",'<span>取 消</span');
        cancelButtonNode.addEvent("click",function(){
            if(onCancel){
                onCancel();
            }
            modalContainerNode.destroy();
        });
    },
    popConfirm: function(ev,content,onConfirm,onCancel,placement){
        if(!placement) placement = "rightTop";

        var popoverNode = new Element("div",{"class":"ant-popover ant-popover-placement-" + placement}).inject(this.contentNode.getElements('body')[0]);

        var popoverContentNode = new Element("div",{"class":"ant-popover-content"}).inject(popoverNode);
        var popoverArrowNode = new Element("div",{"class":"ant-popover-arrow"}).inject(popoverContentNode);
        var popoverInnerNode = new Element("div",{"class":"ant-popover-inner"}).inject(popoverContentNode);
        var popoverInnerContentNode = new Element("div",{"class":"ant-popover-inner-content"}).inject(popoverInnerNode);

        var popoverMessageNode = new Element("div",{"class":"ant-popover-message"}).inject(popoverInnerContentNode);
        var popoverMessageIconNode = new Element("i",{"class":"anticon anticon-exclamation-circle"}).inject(popoverMessageNode);
        popoverMessageIconNode.set("html",'<svg viewBox="64 64 896 896" focusable="false" class="" data-icon="exclamation-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm-32 232c0-4.4 3.6-8 8-8h48c4.4 0 8 3.6 8 8v272c0 4.4-3.6 8-8 8h-48c-4.4 0-8-3.6-8-8V296zm32 440a48.01 48.01 0 0 1 0-96 48.01 48.01 0 0 1 0 96z"></path></svg>');
        var popoverMessageTitleNode = new Element("div",{"class":"ant-popover-message-title"}).inject(popoverMessageNode);

        popoverMessageTitleNode.set("text",content);

        var popoverButtonsNode = new Element("div",{"class":"ant-popover-buttons"}).inject(popoverInnerContentNode);
        var okButtonNode = new Element("button",{"class":"ant-btn ant-btn-primary ant-btn-sm"}).inject(popoverButtonsNode);
        okButtonNode.set("html","<span>确定</span>");

        okButtonNode.addEvent("click",function(){
            if(onConfirm){
                onConfirm();
            }
            popoverNode.destroy();
        });

        var cancelButtonNode = new Element("button",{"class":"ant-btn ant-btn-sm"}).inject(popoverButtonsNode);
        cancelButtonNode.set("html","<span>取消</span>");

        cancelButtonNode.addEvent("click",function(){
            if(onCancel){
                onCancel();
            }
            popoverNode.destroy();
        });

        var position = ev.target.getPosition();
        var size = popoverNode.getSize();
        var left,top;
        switch (placement) {
            case 'leftTop':
                left = position.x -  (size.x);
                top = position.y;
                break;
            case 'top':
                left = position.x -  (size.x)/2 + (ev.target.getSize().x)/2;
                top = position.y - size.y;
                break;
            case 'rightTop':
                left = position.x + ev.target.getSize().x;
                top = position.y;
                break;
            default:
                left = position.x + ev.target.getSize().x;
                top = position.y;
        }
        popoverNode.setStyles({
            "left": left,
            "top": top
        })
    },
    dropdown : function(ev,contentNode,pos){
        var dropdownNode = new Element("div",{"class":"ant-dropdown"}).inject(document.body);
        var position = ev.target.getPosition();

        contentNode.inject(dropdownNode);
        var size = dropdownNode.getSize();
        var left,top;
        if(!pos){
            left = position.x;
            top = position.y + ev.target.getSize().y;
        }
        if(pos && pos==="right"){
            left = position.x - size.x + ev.target.getSize().x;
            top = position.y + ev.target.getSize().y;
        }
        if((position.y + dropdownNode.getSize().y) > document.body.getSize().y){
            top = position.y - dropdownNode.getSize().y
        }
        dropdownNode.setStyles({
            "left": left,
            "top": top
        });

        document.body.addEvent("mousedown",function(e){
            if(!e.target.getParent(".ant-dropdown")){
                document.body.getElements(".ant-dropdown").hide();
            }
        }.bind(this));
        return dropdownNode;
    },
    emptyDlg:function(ev,contentNode){
        contentNode.inject(document.body);
        var position = ev.target.getPosition();
        var size = dropdownNode.getSize();
        var left,top;
        left = position.x;
        top = position.y + ev.target.getSize().y;
        dropdownNode.setStyles({
            "left": left,
            "top": top
        });
        contentNode.inject(dropdownNode);
        document.body.addEvent("mousedown",function(e){
            if(!e.target.getParent(".ant-popover")){
                document.body.getElements(".ant-popover").hide();
            }
        }.bind(this));
        return dropdownNode;
    },
    drawer:function (title,contentNode,width,onOk,onCancel){
        var drawerContainerNode = new Element("div").inject(document.body);
        drawerContainerNode.set("class","wps-ant-drawer wps-ant-drawer-open edit-dept-drawer");
        var drawerMaskNode = new Element("div",{"class":"wps-ant-drawer-mask"}).inject(drawerContainerNode);
        var drawerWrapNode = new Element("div",{"class":"wps-ant-drawer-content-wrapper"}).inject(drawerContainerNode);
        if(width){
            drawerWrapNode.setStyle("width",width);
        }else {
            drawerWrapNode.setStyle("width","550px");
        }

        var drawerContentNode = new Element("div.wps-ant-drawer-content").inject(drawerWrapNode);
        var drawerBodyWrdpNode = new Element("div.wps-ant-drawer-wrapper-body").inject(drawerContentNode);

        var drawerHeaderNode = new Element("div.wps-ant-drawer-header").inject(drawerBodyWrdpNode);
        var drawerHeaderTitleNode = new Element("div.wps-ant-drawer-title").inject(drawerHeaderNode);

        drawerHeaderTitleNode.set("text",title);

        var drawerBodyNode = new Element("div.wps-ant-drawer-body").inject(drawerBodyWrdpNode);
        drawerBodyNode.set("style","height: calc(100% - 55px); overflow: auto; padding-bottom: 53px;");

        var drawerContentNode = new Element("div.drawer-content").inject(drawerBodyNode);
        contentNode.inject(drawerContentNode)

        var drawerFooterNode = new Element("div.drawer-footer").inject(drawerBodyNode);
        cancelBtn = new Element("button",{
            "type":"button",
            "class":"ant-btn ant-btn-ghost",
            "style":"margin-right: 8px;",
            "html" : "<span>取消</span>"
        }).inject(drawerFooterNode);
        okBtn = new Element("button",{
            "type":"button",
            "class":"ant-btn ant-btn-primary",
            "html" : "<span>确定</span>"
        }).inject(drawerFooterNode);
        okBtn.addEvent("click",function(){
            if(onOk){
                onOk();
            }
            drawerContainerNode.destroy();
        });
        cancelBtn.addEvent("click",function(){
            if(onCancel){
                onCancel();
            }
            drawerContainerNode.destroy();
        });
        drawerMaskNode.addEvent("click",function(){
            if(onCancel){
                onCancel();
            }
            drawerContainerNode.destroy();
        });
    }
});
Ant.Pagination = new Class({
    Implements: [Events, Options],
    options: {
        "page": 1,
        "pageSize": 10,
        "showNumber": true,
        "showText": true
    },
    initialize: function (target, options) {
        this.setOptions(options);
        if (typeof (target) == "string") {
            this.target = $(target);
        } else {
            this.target = target;
        }
        this.total = this.options.total;
        this.currentPage = 0;
        this.pageSize = this.options.pageSize;
        this.pageNode = new Element('ul',{"class":"ant-pagination ant-table-pagination"});
        this.target.empty();
        this.pageNode.inject(this.target);
    },
    create: function (panel) {
        panel.empty();
        if (this.options.showText) panel.grab(this.createText());

        if (this.currentPage > 0) {

            var prev = new Element("li",{"class":"ant-pagination-item"});

            var prevLink = new Element('a', {
                'text': '上一页',
                'href': 'javascript:void(null)',
                'events': {
                    'click': this.click.bind(this, this.currentPage - 1)
                }
            }).inject(prev);

            panel.grab(prev);
        }
        if (this.options.showNumber) {
            var beginInx = this.currentPage - 2 < 0 ? 0 : this.currentPage - 2;
            var endIdx = this.currentPage + 2 > this.page ? this.page : this.currentPage + 2;
            if (beginInx > 0) panel.grab(this.createNumber(0));
            if (beginInx > 1) panel.grab(this.createNumber(1));
            if (beginInx > 2) panel.grab(this.createSplit());
            for (var i = beginInx; i < endIdx; i++) {
                panel.grab(this.createNumber(i));
            }
            if (endIdx < this.page - 2) panel.grab(this.createSplit());
            if (endIdx < this.page - 1) panel.grab(this.createNumber(this.page - 2));
            if (endIdx < this.page) panel.grab(this.createNumber(this.page - 1));
        }
        if (this.currentPage < this.page - 1) {
            var next = new Element("li",{"class":"ant-pagination-item"});

            var nextLink = new Element('a', {
                'text': '下一页',
                'href': 'javascript:void(null)',
                'events': {
                    'click': this.click.bind(this, this.currentPage + 1)
                }
            }).inject(next);
            panel.grab(next);
        }

    },
    createNumber: function (i) {
        var li = new Element("li",{"class":"ant-pagination-item"});
        var a = new Element('a', {
            'text': i + 1,
            'href': 'javascript:void(null)',
            'events': {'click': this.click.bind(this, i)}
        }).inject(li);
        if (i === this.currentPage) {
            li.set('class', "ant-pagination-item ant-pagination-item-active");
        }
        return li;
    },
    createSplit: function () {
        var li = new Element("li",{"class":"ant-pagination-jump-next ant-pagination-jump-next-custom-icon"});
        var span = new Element('span', {'text': '...', 'class': "ant-pagination-item-ellipsis"}).inject(li);
        return li
    },
    createText: function () {
        return new Element('li', {
            'class':"ant-pagination-total-text",
            'text': '共' + this.total + ' ,第' + (this.currentPage + 1) + '/' + (this.page) + '页'
        });
    },
    click: function (index) {
        this.currentPage = index;
        this.load();
        this.fireEvent('afterLoad', [this.currentPage + 1]);
    },
    load: function () {
        this.fireEvent('beforeLoad');
        this.page = Math.ceil(this.total / this.pageSize);
        this.create(this.pageNode);

    },
    reload: function (param) {
        this.currentPage = 0;
        this.load();
    },
    setpageSize: function (pageSize) {
        this.pageSize = pageSize;
        this.reload();
    }
});
Ant.Table = new Class({
    Implements: [Events, Options],
    options: {
        "pageSize": 10,
        "page":1,
        "pagination": true,
        "search": false,
        "columns": [],
        "title": "",
        "searchItemList": [],
        "opButtonList":[]
    },
    initialize: function (target, options) {
        this.setOptions(options);
        this.searchItemList = this.options.searchItemList;
        this.opButtonList = this.options.opButtonList;
        this.columns = this.options.columns;
        this.contentNode = target;
        this.contentNode.empty();
    },
    load: function () {
        this.createTitle();
        this.createSearch();
        this.createOp();
        this.createTable();
        this.createPagination();
    },
    reload: function (param) {
        this.options.page = 1;
        this.createTbody();
        this.createPagination();
    },
    getSelects: function () {
        var arr = [];
        this.contentNode.getElements('input[name="selectItem"]').each(function (item) {
            if (item.checked) {
                arr.push(item.getParent().getParent().retrieve("data"));
            }
        });
        return arr;
    },
    createPagination: function () {
        if (this.paginationNode) this.paginationNode.destroy();
        this.paginationNode = new Element("div", {"style":"height:32px;line-height:32px"}).inject(this.contentNode);

        new Ant.Pagination(this.paginationNode, {
            "total": this.total,
            "pageSize": this.options.pageSize,
            "showNumber": true,
            "showText": true,
            "onAfterLoad": function (data) {

                if(this.contentNode.getElements('input[name="selectAll"]').length) this.contentNode.getElements('input[name="selectAll"]')[0].checked = '';
                this.options.page = data;
                this.createTbody();
            }.bind(this)
        }).load();

    },
    createOp: function () {
        this.opNode = new Element("div",{"style":"margin-bottom: 16px;margin-top: 16px;"}).inject(this.contentNode);

        this.opButtonList.each(function (opButton) {
            var opButtonNode = new Element("a", {
                "class": "ant-btn ant-btn-primary",
                "style":"margin-right:8px",
                "text": opButton.text
            }).inject(this.opNode);
            if(opButton.class){
                opButtonNode.set("class",opButton.class);
            }
            if (opButton.action) {
                opButtonNode.addEvent("click", function (ev) {
                    opButton.action(ev, this);
                }.bind(this));
            }
        }.bind(this));

    },
    createSearch: function () {
        if(!(this.searchItemList&&this.searchItemList.length>0)){
            return ;
        }
        this.searchItemNode = new Element("div", {
            "class": "ant-form ant-form-inline"
        }).inject(this.contentNode);
        this.searchItemList.each(function (searchItem) {
            var itemNode;

            if (searchItem.type === "date" || searchItem.type === "input") {
                itemNode = new Element("input", {
                    "class": "ant-input",
                    "name": searchItem.name,
                    "id":searchItem.name,
                    "placeholder": searchItem.title,
                    "style": "margin:5px;"
                }).inject(this.searchItemNode);
                if(searchItem.width){
                    itemNode.setStyle("width",searchItem.width);
                }else{
                    itemNode.setStyle("width","150px");
                }
                if (searchItem.click){
                    itemNode.set("readonly",true);
                }
                if (searchItem.type === "date") {
                    laydate.render({
                        elem: '#' + searchItem.name
                    });
                    return false;

                    itemNode.set("readonly",true);
                    new MWF.widget.Calendar(itemNode, {
                        "style": "xform",
                        "onComplate": function () {
                        }
                    });
                }
            }
            if (searchItem.type === "select") {
                var itemNode = new Element("select", {
                    "style": "width:200px;margin:5px;",
                    "class":"ant-input",
                    "name": searchItem.name
                }).inject(this.searchItemNode);

                searchItem.options.each(function (option) {
                    new Element("option", {
                        "text": option.split("|")[0],
                        "value": option.split("|").length > 1 ? option.split("|")[1] : option.split("|")[0]
                    }).inject(itemNode);
                });
            }
            if (searchItem.click) {
                itemNode.addEvent("click", function (ev) {
                    searchItem.click(ev, itemNode);
                });
            }
        }.bind(this));
        this.searchOkButton = new Element("a", {
            "class": "ant-btn ant-btn-primary",
            "style": "margin:5px;",
            "text": "搜索"
        }).inject(this.searchItemNode).addEvent("click", function () {

            this.options.page = 1;
            this.createTbody();
            this.createPagination();
        }.bind(this));
        this.searchCancleButton = new Element("a", {
            "class": "ant-btn",
            "style": "margin:5px;",
            "text": "取消"
        }).inject(this.searchItemNode).addEvent("click", function () {
            this.searchItemList.each(function (item) {
                this.contentNode.getElements('[name=' + item.name + ']').set("value", "");
            }.bind(this));

            this.options.page = 1;
            this.createTbody();
            this.createPagination();
        }.bind(this));
    },
    createTable: function () {
        this.contentTableNode = new Element("div",{"class":"ant-table"}).inject(this.contentNode);
        this.tableNode = new Element("table").inject(this.contentTableNode);
        this.createThead();
        this.createTbody();
    },
    createThead: function () {

        this.theadNode = new Element("thead",{"class":"ant-table-thead"}).inject(this.tableNode);

        var trNode = new Element("tr").inject(this.theadNode);

        this.columns.each(function (column) {

            var thNode = new Element("th",{"class":"ant-table-column-title"}).inject(trNode);
            if (column.title) thNode.set("text", column.title);
            if (column.width) thNode.setStyle("width", column.width);
            if (column.type) {
                if (column.type === "checkbox") {
                    var checkAllNode = new Element("input", {"type": "checkbox", "name": "selectAll"}).inject(thNode);
                    checkAllNode.addEvent("click", function () {

                        this.contentNode.getElements('input[name="selectItem"]').each(function (item) {
                            if (checkAllNode.checked) {
                                item.checked = 'checked';
                            } else {
                                item.checked = '';
                            }
                        }.bind(this));
                    }.bind(this));
                }
            }
        }.bind(this));
    },
    createEmpty : function (){
        this.emptyNode = new Element("div",{"class":"ant-table-placeholder"}).inject(this.contentNode);
        this.emptyNode.set("text","暂无数据");
    },
    createTitle : function (){
        this.titleNode = new Element("div",{"class":"title"}).inject(this.contentNode);
        this.titleNode.set("text",this.options.title);
        this.titleNode.set("style","margin-bottom: 16px;");
    },
    createTbody: function () {

        if (this.tbodyNode) this.tbodyNode.destroy();
        this.tbodyNode = new Element("tbody",{"class":"ant-table-tbody"}).inject(this.tableNode);
        this.fireEvent('beforeLoadData');

        if(this.dataList.length === 0){
            this.createEmpty();
        }
        this.dataList.each(function (data) {

            var trNode = new Element("tr",{"class":"ant-table-row"}).inject(this.tbodyNode);
            trNode.store("data", data);
            this.columns.each(function (column) {
                var thNode = new Element("td").inject(trNode);

                if(column.formatter){
                    column.formatter(data,thNode);
                }else{
                    if(column.field){
                        var pathArr = column.field.split(".");
                        var v ;
                        pathArr.each(function (path){
                            if(!v){
                                v = data[path];
                            }else {
                                v = v[path];
                            }
                        })
                        thNode.set("text",v);
                    }
                }
                if (column.type) {
                    if (column.type === "operation") {
                        column.opButtonList.each(function (opButton) {
                            var opButtonNode = new Element("a", {
                                "class": "ant-btn",
                                "text": opButton.text
                            }).inject(thNode);
                            if (opButton.action) {
                                opButtonNode.addEvent("click", function (ev) {
                                    opButton.action(data,this,ev);
                                }.bind(this));
                            }
                        }.bind(this));
                    }
                    if (column.type === "checkbox") {
                        var checkItemNode = new Element("input", {
                            "type": "checkbox",
                            "name": "selectItem"
                        }).inject(thNode);

                        checkItemNode.addEvent("click", function (event) {
                            if (event.target.checked) {
                                var i = 0;
                                this.contentNode.getElements('input[name="selectItem"]').each(function (chk) {
                                    if (!chk.checked) {
                                        i = i + 1;
                                    }
                                });
                                if (i === 0) {
                                    this.contentNode.getElements('input[name="selectAll"]')[0].checked = 'checked';
                                }
                            } else {
                                this.contentNode.getElements('input[name="selectAll"]')[0].checked = '';
                            }
                        }.bind(this));
                    }
                }
            }.bind(this));
        }.bind(this));
    }
});



