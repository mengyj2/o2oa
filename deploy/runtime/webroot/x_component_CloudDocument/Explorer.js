
o2.xApplication.CloudDocument.Explorer = new Class({
    Implements: [Options, Events],
    options: {
        "style": "default",
        "page" : 1,
        "explorer": "Explorer",
        "pageSize":1000,
    },
    initialize: function(app,node,options){
        this.setOptions(options);
        this.app = app;
        this.node = $(node);
        this.initApp();
        this.path = "../x_component_CloudDocument/$" + this.options.explorer+"/";
        this.templatePath =  this.path + this.options.style;
        this.initData();
    },
    initApp : function (){
        this.srv = this.app.srv;
        this.wi = this.app.wi;
        this.util = this.app.util;
        this.menuType = this.app.menuType;

    },
    reload : function(){
        if(this.menuType === "folder"){
            this.contentNode.destroy();
            var folderList = this.getFolderList(this.folderId);
            var fileList = this.getFileList(this.folderId);
            folderList.append(fileList);
            this.dataList = folderList;
            this.loadContent();
        }else {
            this.initData();
        }
    },
    initData : function (){
        this.folderId = "-1";
        this.folderName = "我的文档";

        var folderList = this.getFolderList(this.folderId);
        var fileList = this.getFileList(this.folderId);
        folderList.append(fileList);

        this.dataList = folderList;
        this._initData();

    },
    getFolderList : function(parentId,isRemove){
        var dataList = [];
        this.srv.execute("getFolderList", {
            "folderId" : parentId,
            "isRemove" : isRemove ? isRemove : false
        },function(json) {
            dataList = json;
            dataList.each(function(d){
                d.fileType = "folder";
                d.fileSize = "-";
            });
        }.bind(this));
        return dataList;
    },
    getFileList : function(parentId){
        var dataList = [];
        var data = {
            "page" : this.options.page,
            "pageSize" : this.options.pageSize,
            "folderId" : parentId
        };
        this.srv.execute("queryDocumentByPage", data,function(json) {
            dataList = json.dataList;
            dataList.each(function(d){
                d.name = d.fileName;
            });
        }.bind(this));
        return dataList;
    },
    _initData : function (){
        var toolbarUrl = this.path+"toolbar.json";
        o2.getJSON(toolbarUrl, function(json){
            this.toolBarJson = json;
            this.load();
        }.bind(this));
    },
    load: function(){
        this.node.empty();
        this.loadHeader();
        this.loadContent();
    },
    loadFile : function(){
        this.contentNode.destroy();
        var folderList = this.getFolderList(this.folderId);
        var fileList = this.getFileList(this.folderId);
        folderList.append(fileList);
        this.dataList = folderList;
        this.loadBread(this.folderName,this.folderId);
        this.loadContent();
    },
    loadTagFile : function(tag){
        this.srv.execute("queryTagByPage", {
            "page" : this.options.page,
            "pageSize" : this.options.pageSize,
            "tag" : tag
        },function(json) {
            json.dataList.each(function(d){
                d.name = d.fileName;
            }.bind(this));
            this.dataList = json.dataList;
        }.bind(this));
        this.contentNode.destroy();
        this.loadTagBread(tag);
        this.loadContent();
    },
    loadTagBread : function(tagName){
        this.breadNode.empty();
        var breadNode = new Element("div.root_search").inject(this.breadNode);
        new Element("a.root_search_actions",{
            html:'<i class="iconfont icon_back "></i><span>返回</span>'
        }).inject(breadNode).addEvent("click",function(){
            this.app.loadDocument();
        }.bind(this));
        new Element("div.root_search_value",{
            "html":'<div class="title">标签：<span class="value">'+ tagName +'</span></div>'
        }).inject(breadNode);
    },
    loadContent: function(){

        this.contentNode = new Element("div.root_content").inject(this.node);
        this.view = new o2.xApplication.CloudDocument[this.options.explorer].View(this.contentNode, this, this.dataList );
        this.view.load();
    },
    loadHeader:function (){
        this.rootHeadNode = new Element("div.root_head").inject(this.node);
        this.breadNode = new Element("span",{"class":"breadcrumb ant-breadcrumb"}).inject(this.rootHeadNode);
        this.actionNode = new Element("div.root_head_tool").inject(this.rootHeadNode);
        //this.loadBread();
        this.loadBread("我的文档","-1","root");
        this.loadToolbar();
    },
    loadBread : function (name,folderId,type){
        var breadNode = new Element("span").inject(this.breadNode);
        var linkNode = new Element("span.ant-breadcrumb-link").inject(breadNode);
        new Element("span.ant-breadcrumb-separator",{"text":"/"}).inject(breadNode);
        linkNode.set("html",'<a href="javascript:;"><i class="iconfont icon_folder"></i>'+ name +'</a>');
        if(type==="root"){
            linkNode.getElement("i").hide();
        }
        linkNode.getElement("a").addEvent("click",function(){
            this.folderId = folderId;
            this.folderName = name;
            this.loadFile();
            breadNode.getAllNext().destroy();
        }.bind(this));
    },
    loadToolbar: function(){
        this.toolBarJson.headToolBar.each(function(tool){
            this.createHeadToolbarItemNode(tool);
        }.bind(this));
    },
    createHeadToolbarItemNode : function( tool ){
        var toolItemNode = new Element("button", {
            "style": tool.style ? tool.style : "",
            "class":"ant-btn dropdown-button ant-dropdown-trigger"
        });
        toolItemNode.store("toolData", tool );
        if( tool.title ){
            var textNode =  new Element("span.text", {
                "text": tool.title
            });
            if( tool.text )textNode.set("title", tool.text);
            textNode.inject(toolItemNode);
        }
        new Element("i",{"class":"iconfont icon_down2","style":"font-size: 10px"}).inject(toolItemNode);
        toolItemNode.inject(this.actionNode);
        this.setToolbarItemEvent(toolItemNode);
    },
    setToolbarItemEvent:function(toolItemNode){
        var _self = this;
        toolItemNode.addEvents({
            "click": function (ev) {
                var data = this.retrieve("toolData");
                if( _self[data.action] )_self[data.action].apply(_self,[ev]);
            }
        })
    },
    upload : function (){
        o2.require("o2.widget.Upload", null, false);
        var upload = new o2.widget.Upload(document.body, {
            "action": o2.Actions.get("x_onlyoffice_assemble_control").action,
            "method": "addAttachment",
            "multiple":false,
            "accept" : ".doc,.docx,.ppt,.pptx,.xls,.xlsx",
            "onCompleted": function(json){
                var documentId = json.id;
                o2.Actions.load("x_onlyoffice_assemble_control").OnlyofficeAction.get(documentId,function( json ){
                    var document = json.data;
                    var fileName = document.fileName;
                    this.srv.execute("createDocument", {
                        "fileName": fileName.substr(0,fileName.lastIndexOf(".")),
                        "fileType" : document.fileType.replace(".",""),
                        "folderId": this.folderId,
                        "teamId" : this.teamId,
                        "documentId" : documentId,
                        "fileSize" : document.fileSize
                    },function(json) {
                        this.wi.message("success","创建成功");
                        this.reload();
                    }.bind(this));
                }.bind(this),null,false );
            }.bind(this)
        });
        upload.load();
    },
    new : function(ev){
        var bodyNode = new Element("div");
        bodyNode.loadHtml(this.templatePath + "/new.html", { "module": this,"bind": {"lp": this.lp}}, function(){
            var newDropNode = this.wi.dropdown(ev,bodyNode);
        }.bind(this));
    },
    newFile : function(ev){
        if(ev.target.getParent(".new_panel")){
            var fileType = ev.target.getParent(".new_panel").get("fileType");
        }
        var bodyNode = new Element("div");
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);

        var data = {
            "fileType":fileType,
            "folderId" : this.folderId,
            "folderName" : this.folderName
        };

        bodyNode.loadHtml(this.templatePath + "/newFile.html", { "module": this,"bind": data}, function(){
            var modal = this.wi.modal("新建",bodyNode,footerNode,{"height":"150px","width":"500px"});

            var fileNameNode = modal.getElement(".ant-input");
            var folderNode = modal.getElement(".path-name");
            this.openFolderNode.addEvent("click",function(){
                this.app.openFolder(function(data){
                    if(data){
                        folderNode.set("text",data.name);
                        folderNode.set("folderId",data.id);
                    }
                }.bind(this));
            }.bind(this));
            cancelBtn.addEvent("click",function(){
                modal.destroy();
            }.bind(this));

            okBtn.addEvent("click",function(){
                //createFolder
                this.srv.execute("createDocument", {
                    "fileName": fileNameNode.get("value"),
                    "fileType" : fileType,
                    "teamId" : this.app.teamId,
                    "folderId": folderNode.get("folderId")
                },function(json) {
                    this.wi.message("success","创建成功");
                    modal.destroy();
                    this.reload();
                }.bind(this));

            }.bind(this));
        }.bind(this));
    },
    newFolder : function(){
        var bodyNode = new Element("div");
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);

        var data = {
            "folderId" : this.folderId,
            "folderName" : this.folderName
        };
        bodyNode.loadHtml(this.templatePath + "/newFolder.html", { "module": this,"bind": data}, function(){
            var modal = this.wi.modal("新建文件夹",bodyNode,footerNode,{"height":"150px","width":"500px"});

            var fileNameNode = modal.getElement(".ant-input");
            var folderNode = modal.getElement(".path-name");
            this.openFolderNode.addEvent("click",function(){
                this.app.openFolder(function(data){
                    if(data){
                        folderNode.set("text",data.name);
                        folderNode.set("folderId",data.id);
                    }
                }.bind(this));
            }.bind(this));
            cancelBtn.addEvent("click",function(){
                modal.destroy();
            }.bind(this));
            okBtn.addEvent("click",function(){
                //createFolder
                this.srv.execute("createFolder", {
                    "name": fileNameNode.get("value"),
                    "parentId": folderNode.get("folderId"),

                },function(json) {
                    this.wi.message("success","创建成功");
                    modal.destroy();
                    this.reload();
                }.bind(this));
            }.bind(this));
        }.bind(this));
    },
});
o2.xApplication.CloudDocument.Explorer.View = new Class({

    initialize: function( container, app,dataList ){
        this.container = container;
        this.app = app;
        this.dataList = dataList;
        this.initApp();
    },
    initApp : function (){

        this.templatePath = this.app.templatePath;
        this.wi = this.app.wi;
        this.srv = this.app.srv;
        this.path = this.app.path;
        this.util = this.app.util;
        this.menuType = this.app.menuType;
        this.mainApp = this.app.app;
    },
    load : function(){
        this.createListHead();
        if(this.dataList.length === 0){
            this.createEmpty();
        }else{
            o2.loadHtml(this.templatePath + "/file_item.html", function(loaded){
                var html = loaded[0].data;
                this.dataList.each(function(data){
                    this.createFileItem(data,html,"bottom");
                }.bind(this));
            }.bind(this));
        }
    },
    reload:function(){
        this.app.reload();
    },
    createFileItem : function(data,html,pos){
        new o2.xApplication.CloudDocument[this.app.options.explorer].Document(this.fileListNode,data,this,html,pos);
    },
    createListHead : function(){
        this.fileListTitleNode = new Element("div.root_row_title").inject(this.container);
        this.fileListNode = new Element("div.root_row_content").inject(this.container);

        this.fileListTitleNode.loadHtml(this.templatePath + "/file_title.html", {
            "module": this,
            "bind": {"lp": this.lp}
            }, function(){
                this.loadToolbar();
            }.bind(this));
    },
    loadToolbar: function(){
        this.app.toolBarJson.selectToolBar.each(function(tool){
            this.createToolbarItemNode(tool);
        }.bind(this));
    },
    createToolbarItemNode : function( tool ){
        var toolItemNode = new Element("button", {
            "style": tool.style ? tool.style : "",
            "class":"ant-btn ant-btn-link"
        });
        toolItemNode.store("toolData", tool );
        if( tool.title ){
            var textNode =  new Element("span", {
                "text": tool.title
            });
            if( tool.text )textNode.set("title", tool.text);
            textNode.inject(toolItemNode);
        }
        toolItemNode.inject(this.toolbarNode);
        this.setToolbarItemEvent(toolItemNode);
    },
    setToolbarItemEvent:function(toolItemNode){
        var _self = this;
        toolItemNode.addEvents({
            "click": function () {
                var data = this.retrieve("toolData");
                if( _self[data.action] )_self[data.action].apply(_self,[this]);
            }
        })
    },
    selectAll : function(){

        if(this.allSelectedNode.hasClass("ant-checkbox-indeterminate")){
            this.allSelectedNode.removeClass("ant-checkbox-indeterminate");
            this.allSelectedNode.addClass("ant-checkbox-checked");
            //全选
            this.fileListNode.getElements(".ant-checkbox").set("class","ant-checkbox ant-checkbox-checked");
            this.fileListNode.getElements(".root_rows").setStyle("background","rgb(244, 248, 255)") ;
        }else if(this.allSelectedNode.hasClass("ant-checkbox-checked")){
            this.allSelectedNode.removeClass("ant-checkbox-checked");
            //取消全选
            this.fileListNode.getElements(".ant-checkbox").set("class","ant-checkbox");
            this.fileListNode.getElements(".root_rows").setStyle("background","rgb(255, 255, 255)") ;
        }else{
            this.allSelectedNode.addClass("ant-checkbox-checked");
            //全选
            this.fileListNode.getElements(".ant-checkbox").set("class","ant-checkbox ant-checkbox-checked");
            this.fileListNode.getElements(".root_rows").setStyle("background","rgb(244, 248, 255)") ;
        }
        this.setSelected();
    },
    setSelected : function(){
        var selectFileList = this.getSelected();
        if(selectFileList.length===this.fileListNode.getElements(".root_rows").length){
            this.allSelectedNode.set("class","ant-checkbox ant-checkbox-checked");
            this.showFileOp();
        }else if(selectFileList.length>0){
            this.allSelectedNode.set("class","ant-checkbox ant-checkbox-indeterminate");
            this.showFileOp();
        }else{
            this.allSelectedNode.set("class","ant-checkbox");
            this.hideFileOp();
        }
        this.selectCountNode.set("text",selectFileList.length);
    },
    getSelected : function(){
        var fileList = [];
        this.fileListNode.getElements(".ant-checkbox-checked").each(function(ev){
            fileList.push(ev.retrieve("file"));
        }.bind(this));
        return fileList;
    },
    setSelected : function(){

        var selectFileList = this.getSelected();
        if(selectFileList.length===this.fileListNode.getElements(".root_rows").length){
            this.allSelectedNode.set("class","ant-checkbox ant-checkbox-checked");
            this.showFileOp();
        }else if(selectFileList.length>0){
            this.allSelectedNode.set("class","ant-checkbox ant-checkbox-indeterminate");
            this.showFileOp();
        }else{
            this.allSelectedNode.set("class","ant-checkbox");
            this.hideFileOp();
        }
        this.selectCountNode.set("text",selectFileList.length);
    },
    showFileOp : function(){
        this.headRowNode.getElement(".file-op").show();
        this.headRowNode.getElement(".file-name").hide();
        this.headRowNode.getElement(".file-size").hide();
        this.headRowNode.getElement(".update-time").hide();
        if(this.headRowNode.getElement(".updater")){
            this.headRowNode.getElement(".updater").hide();
        }
    },
    hideFileOp : function(){
        this.headRowNode.getElement(".file-op").hide();
        this.headRowNode.getElement(".file-name").show();
        this.headRowNode.getElement(".file-size").show();
        this.headRowNode.getElement(".update-time").show();
        if(this.headRowNode.getElement(".updater")){
            this.headRowNode.getElement(".updater").show();
        }
    },
    createEmpty : function (){
        this.fileListNode.loadHtml(this.templatePath + "/file_nofile.html", {
            "module": this,"bind": {"lp": this.lp,"data": {menuType:this.menuType}}}, function(){
        }.bind(this));
    },
    moveMulti : function(){
        var fileList = this.getSelected();
        this.mainApp.openFolder(function(folderData){

            fileList.each(function(data){
                this.srv.execute(data.fileType==="folder"?"moveFolder":"moveDocument", {
                    "documentId": data.id,
                    "folderId" : data.id,
                    "newFolderId" :folderData.id
                },function(json) {

                }.bind(this));
            }.bind(this));
            this.wi.message("success","移动成功");
            this.reload();
        }.bind(this));
    },
    copyMulti : function(){
        var fileList = this.getSelected();
        this.mainApp.openFolder(function(folderData){
            //文件夹的拷贝可能有问题
            fileList.each(function(data){
                this.srv.execute(data.fileType==="folder"?"copyFolder":"copyDocument", {
                    "documentId": data.id,
                    "folderId" : data.id,
                    "newFolderId" :folderData.id
                },function(json) {

                }.bind(this));
            }.bind(this));
            this.wi.message("success","拷贝成功");
            this.reload();
        }.bind(this));
    },
    removeMulti : function(){
        var fileList = this.getSelected();
        fileList.each(function(data){
            this.srv.execute(data.fileType==="folder"?"removeFolder":"removeDocument", {
                "documentId": data.id,
                "folderId" : data.id,
                "soft" :true
            },function(json) {

            }.bind(this));
        }.bind(this));
        this.wi.message("success","删除成功");
        this.reload();
    },
});
o2.xApplication.CloudDocument.Explorer.Document = new Class({
    initialize: function(container, data, app,html,pos){
        this.container = container;
        this.data = data;
        this.html = html;
        this.app = app;
        this.pos = pos;
        this.initApp();
        this.load();
    },
    initApp : function (){
        this.wi = this.app.wi;
        this.util = this.app.util;
        this.srv = this.app.srv;
        this.path = this.app.path;
        this.menuType = this.app.menuType;
        this.mainApp = this.app.mainApp;
        this.templatePath = "../x_component_CloudDocument/$Explorer/default";
    },
    load : function (){

        if(this.data.fileType!=="folder"){
            this.data.fileSize = this.util.getFileSize(this.data.fileSize);
        }
        this.data.time = this.util.timestampFormat(Date.parse(this.data.updateTime)/1000);
        //.format("%m-%d %H:%M");

        this.html = this.html.bindJson(this.data);
        var tmpNode = new Element("div",{"html":this.html});
        var itemNode = tmpNode.getFirst().inject(this.container,this.pos);
        var fileNameNode = itemNode.getElement(".name");
        var fileFavNode = itemNode.getElement(".favorite-star");
        if(this.data.fav && fileFavNode){
            fileFavNode.show();
        }
        if(this.mainApp.searchInputNode.get("value")!==""){
            fileNameNode.set("html",fileNameNode.get("text").replace(this.mainApp.searchInputNode.get("value"),"<font color=red>"+this.mainApp.searchInputNode.get("value")+"</font>"))
        }
        fileNameNode.addEvent("click",function(){
            this.open();
        }.bind(this));
        var tagListNode = itemNode.getElement(".tags-inline");
        if(tagListNode){
            this.data.tagList.each(function(tag){
                var tagNode = new Element("span.tag-item",{"text":tag}).inject(tagListNode);
                tagNode.addEvent("click",function(){
                    this.app.app.loadTagFile(tag);
                }.bind(this));
            }.bind(this));
        }
        //moreaction
        if(itemNode.getElement(".icon_more2")){
            var moreActionNode = itemNode.getElement(".icon_more2").getParent();
            moreActionNode.addEvent("click",function(ev){
                this.loadMoreAction(ev);
            }.bind(this));
        }
        //checkbox
        var checkbox = itemNode.getElement(".ant-checkbox");
        if(checkbox){
            checkbox.store("file",this.data);
            checkbox.addEvent("click",function(){
                if(checkbox.hasClass("ant-checkbox-checked")){
                    checkbox.removeClass("ant-checkbox-checked");
                    checkbox.getParent(".root_rows").setStyle("background","rgb(255, 255, 255)") ;
                }else{
                    checkbox.addClass("ant-checkbox-checked");
                    checkbox.getParent(".root_rows").setStyle("background","rgb(244, 248, 255)") ;
                }
                this.app.setSelected();
            }.bind(this));
        }

    },
    loadMoreAction : function (ev){
        var itemActionUrl = this.path+"itemAction.json";
        this.moreActionNode = new Element("ul",{"class":"ant-dropdown-menu"});
        this.moreActionNode.set("style","min-width: 140px;");
        o2.getJSON(itemActionUrl, function(json){
            json.each(function(itemAction){
                this.createActionItemNode(itemAction);
            }.bind(this));
            this.documentDropNode = this.wi.dropdown(ev,this.moreActionNode,"right");
        }.bind(this));
    },
    createActionItemNode : function( actionItem ){
        var actionItemNode = new Element("li", {
            "class":"ant-dropdown-menu-item"
        });
        if( actionItem.title ){
            var textNode =  new Element("span", {
                "text": actionItem.title
            });
            if( actionItem.text )textNode.set("title", actionItem.text);
            textNode.inject(actionItemNode);
        }
        if(actionItem.show){
            var flag = eval(actionItem.show,this);
            if(!flag) return;
        }
        actionItemNode.inject(this.moreActionNode);
        actionItemNode.addEvent("click",function (){
            if( this[actionItem.action] ){
                this[actionItem.action]();
            }
        }.bind(this));
    },
    download : function(){
        var action = o2.Actions.get("x_onlyoffice_assemble_control");
        var host = action.action.getAddress();
        var path = "/jaxrs/onlyoffice/file/" + this.data.documentId + "/0?xtoken="

        this.srv.execute("getDocumentToken", {
            "documentId": this.data.id
        },function(json) {
            var xtoken = json.fileToken;
            window.open(host + path + xtoken);
        }.bind(this));
    },
    gpgDownload : function(){
        this.hideDrop();
        var data = this.data;
        var bodyNode = new Element("div");
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);

        bodyNode.loadHtml(this.templatePath + "/gpg.html", { "module": this,"bind": data}, function(){
            var modal = this.wi.modal("GPG加密key选择",bodyNode,footerNode,{"height":"80px","width":"500px"});

            var fileNameNode = modal.getElement(".ant-input");
            var folderNode = modal.getElement(".path-name");

            bodyNode.getElement("[data-o2-element=openFolderNode]").hide();

            cancelBtn.addEvent("click",function(){
                modal.destroy();
            }.bind(this));

            okBtn.addEvent("click",function(){
                //createFolder
                if(this.data.name === fileNameNode.get("value")){
                    this.wi.message("error","名称没有改变");
                }else{
                    this.srv.execute(data.fileType==="folder"?"renameFolder":"renameDocument", {
                        "documentId": data.id,
                        "folderId" : data.id,
                        "name" : fileNameNode.get("value")
                    },function(json) {
                        this.wi.message("success","重命名成功");
                        this.reload();
                        modal.destroy();
                    }.bind(this));
                }
            }.bind(this));
        }.bind(this));
    },
    open: function(){
        var fileType = this.data.fileType;
        if(fileType === "folder"){
            this.app.app.folderId = this.data.id;
            this.app.app.folderName = this.data.name;
            //this.createBread(this.data.name,this.data.id);
            this.app.app.loadFile();
        }else{
            this.srv.do("cloudDocumentSrv","addLatest", {
                "documentId" : this.data.id
            },function(json) {

                this.srv.do("cloudDocumentSrv","getDocumentOnline", {
                    "documentId" : this.data.id
                },function(json) {

                    var curOnline = json.length;
                    var nameArr = [];
                    json.each(function (d){
                        nameArr.push(d.personName);
                    })
                    if(this.data.online && curOnline>=this.data.online){
                        var bodyNode = new Element("div");

                        var tipNode = new Element("div",{"html":"\"" + this.data.fileName + "\"只允许" + this.data.online + "个用户同时在线查看。" })
                        tipNode.inject(bodyNode);
                        var tip2Node = new Element("div",{
                            "html" : "当前在线查看用户:" + nameArr.join(",")
                        }).inject(bodyNode);
                        var footerNode = new Element("div");

                        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);

                        var modal = this.wi.modal("同时在线查看提示",bodyNode,footerNode);

                        okBtn.addEvent("click",function(){
                            modal.destroy();
                        }.bind(this));

                    }else {
                        var appId = "CloudDocumentEditor"+this.data.documentId;
                        var options = {
                            "documentId": this.data.id,
                            "mode":"edit"
                        };
                        layout.openApplication(appId,  "CloudDocumentEditor", options);
                    }
                }.bind(this))


            }.bind(this));
        }
    },
    remove: function(){
        this.hideDrop();
        this.wi.confirm("删除确认","您确定要删除\"" + this.data.name+"\"",null,function(){
            this.srv.execute(this.data.fileType==="folder"?"removeFolder":"removeDocument", {
                "documentId": this.data.id,
                "folderId" : this.data.id,
                "soft" :true
            },function(json) {
                this.wi.message("success","删除成功");
                this.reload();
            }.bind(this));
        }.bind(this));
    },
    hideDrop : function (){
        //this.mainApp.documentDropNode.destroy();
    },
    move : function(){
        debugger
        this.hideDrop();
        this.mainApp.openFolder(function(folderData){
            this.srv.execute(this.data.fileType==="folder"?"moveFolder":"moveDocument", {
                "documentId": this.data.id,
                "folderId" : this.data.id,
                "newFolderId" :folderData.id
            },function(json) {
                this.wi.message("success","移动成功");
                this.reload();
            }.bind(this));
        }.bind(this));
    },
    reload : function(){
        this.app.reload();
        //this.app.app.loadFileList();
    },
    copy:function (){
        this.hideDrop();
        this.mainApp.openFolder(function(folderData){
            this.srv.execute(this.data.fileType==="folder"?"copyFolder":"copyDocument", {
                "documentId": this.data.id,
                "folderId" : this.data.id,
                "newFolderId" :folderData.id
            },function(json) {
                this.wi.message("success","拷贝成功");
                this.reload();
            }.bind(this));
        }.bind(this));
    },
    rename:function (){
        this.hideDrop();
        var data = this.data;
        var bodyNode = new Element("div");
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);

        bodyNode.loadHtml(this.templatePath + "/"+ (data.fileType==="folder"?"newFolder" : "newFile")+".html", { "module": this,"bind": data}, function(){
            var modal = this.wi.modal("重命名",bodyNode,footerNode,{"height":"80px","width":"500px"});

            var fileNameNode = modal.getElement(".ant-input");
            var folderNode = modal.getElement(".path-name");

            bodyNode.getElement("[data-o2-element=openFolderNode]").hide();

            cancelBtn.addEvent("click",function(){
                modal.destroy();
            }.bind(this));

            okBtn.addEvent("click",function(){
                //createFolder
                if(this.data.name === fileNameNode.get("value")){
                    this.wi.message("error","名称没有改变");
                }else{
                    this.srv.execute(data.fileType==="folder"?"renameFolder":"renameDocument", {
                        "documentId": data.id,
                        "folderId" : data.id,
                        "name" : fileNameNode.get("value")
                    },function(json) {
                        this.wi.message("success","重命名成功");
                        this.reload();
                        modal.destroy();
                    }.bind(this));
                }
            }.bind(this));
        }.bind(this));
    },
    star:function (){
        this.hideDrop();
        this.srv.execute("addFav", {
            "documentId": this.data.id
        },function(json) {
            this.wi.message("success","添加成功");
            this.reload();
        }.bind(this));
    },
    unstar:function (){
        this.hideDrop();
        this.srv.execute("deleteFav", {
            "documentId": this.data.id
        },function(json) {
            this.wi.message("success","添加成功");
            this.reload();
        }.bind(this));
    },
    share:function (){
        this.hideDrop();
        var bodyNode = new Element("div");

        var footerNode = new Element("div");
        footerNode.setStyle("display","flex")

        var tools = new Element("div.modal-footer-total").inject(footerNode);
        var btns = new Element("div.modal-footer-buttons").inject(footerNode);
        tools.set("style","flex: 1 1 0%;text-align: left;");
        btns.set("style","align-self: flex-end;");
        var cancelBtn = new Element("button",{text:"返回",class:"ant-btn ant-btn-ghost"}).inject(btns);

        var addBtn = new Element("button",{text:"添加成员",class:"ant-btn"}).inject(tools);
        // var removeBtn = new Element("button",{text:"移除成员",class:"ant-btn"}).inject(tools);
        // var aclBtn = new Element("button",{text:"修改权限",class:"ant-btn"}).inject(tools);

        var data = {
            "folderId" : this.folderId,
            "folderName" : this.folderName
        };

        bodyNode.loadHtml(this.templatePath + "/file_share.html", { "module": this,"bind": data}, function(){
            var modal = this.wi.modal("分享设置",bodyNode,footerNode,{"width":"640px"});

            cancelBtn.addEvent("click",function(){
                modal.destroy();
            }.bind(this));

            addBtn.addEvent("click",function(){
                this.addPerson();
            }.bind(this));
            this.loadPersonList();

        }.bind(this));
    },
    addPerson : function(){
        var opt = {
            "types": ["identity"],
            "count": 0,
            "title": "添加成员",
            "values":[],
            "onComplete": function (items) {
                var dataList = [];
                items.each(function(item){
                    dataList.push({
                        person : item.data.woPerson.unique,
                        personName : item.data.woPerson.name,
                        acl : 2
                    })
                })
                this.app.srv.execute("addAcl", {
                    documentId : this.data.id,
                    dataList : dataList
                },function(json) {
                    this.loadPersonList();
                }.bind(this));
            }.bind(this)
        };
        o2.xDesktop.requireApp("Selector", "package", function(){
            new o2.O2Selector(this.mainApp.content, opt);
        }.bind(this), false);
    },
    loadPersonList : function(){
        this.personListNode.empty();
        this.srv.execute("getDocumentAcl", {documentId:this.data.id},function(json) {
            o2.loadHtml(this.templatePath + "/file_person.html", function(loaded){
                var html = loaded[0].data;
                json.each(function(data){
                    this.loadPersonItem(data,html);
                }.bind(this));

            }.bind(this));
        }.bind(this));
    },
    loadPersonItem : function(data,html){
        data.userImg = this.app.util.getAvatar(data.person.split("@")[1]);
        data.userName = data.personName;
        data.aclName = this.app.util.getDocumentAcl(data.acl);

        html = html.bindJson(data);
        var tmpNode = new Element("tbody",{"html":html});

        var itemNode = tmpNode.getFirst().inject(this.personListNode);
        itemNode.getElement(".acl").addEvent("click",function(ev){
            if(data.acl>0) this.setPersonAcl(ev,data);
        }.bind(this));
    },
    setPersonAcl : function(ev,data){
        var bodyNode = new Element("div");
        bodyNode.loadHtml(this.templatePath + "/user_acl.html", { "module": this,"bind": {"lp": this.lp,"user":this.user}}, function(){
            this.newDropNode = this.wi.dropdown(ev,bodyNode);
            this.newDropNode.getElements("a").addEvent("click",function(ev){
                var role = ev.target.get("role");
                if(role==="remove"){
                    this.removeAcl(data.person);
                }else{
                    this.updateAcl(data.person,role);
                }
            }.bind(this));
        }.bind(this));
    },
    updateAcl : function(person,acl){
        this.srv.execute("updateAcl", {
            documentId : this.data.id,
            aclPerson : person,
            acl : acl
        },function(json) {
            this.loadPersonList();
            this.newDropNode.destroy();
        }.bind(this));
    },
    removeAcl : function(person){
        this.srv.execute("removeAcl", {
            documentId : this.data.id,
            aclPerson : person
        },function(json) {
            this.loadPersonList();
            this.newDropNode.destroy();
        }.bind(this));
    },
    history:function (){
        this.hideDrop();
        var bodyNode = new Element("div");
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"关闭",class:"ant-btn ant-btn-ghost"}).inject(footerNode);

        var data = {
            "folderId" : this.folderId,
            "folderName" : this.folderName
        };

        bodyNode.loadHtml(this.templatePath + "/file_version.html", { "module": this,"bind": data}, function(){
            this.versionModal = modal = this.wi.modal("历史版本",bodyNode,footerNode,{width:"640px"});

            cancelBtn.addEvent("click",function(){
                this.versionModal.destroy();
            }.bind(this));
            this.srv.execute("getDocumentVersionList", {
                "documentId": this.data.id
            },function(json) {

                o2.loadHtml(this.templatePath + "/file_version_item.html", function(loaded){
                    var html = loaded[0].data;
                    json.each(function(data){
                        // if(data.version>0) this.loadVersionItem(data,html);
                        this.loadVersionItem(data,html);
                    }.bind(this));

                }.bind(this));
            }.bind(this));

        }.bind(this));
    },
    loadVersionItem : function(data,html){
        data.personName = data.person.split("@")[0];
        data.updateTime = this.util.timestampFormat(Date.parse(data.changeTime)/1000);
        if(data.comment && data.comment!==""){
            data.comment_show = "(" + data.comment + ")"
        }
        html = html.bindJson(data);
        var tmpNode = new Element("tbody",{"html":html});

        //console.log(data.updateTime)
        var itemNode = tmpNode.getFirst().inject(this.versionBodyNode);

        itemNode.getElement(".item-text-desc").addEvent("click",function(){
            var appId = "CloudDocumentEditor"+this.data.documentId;
            var options = {
                "documentId": this.data.id,
                "version" : data.version,
                "mode":"view"
            };
            layout.openApplication(appId,  "CloudDocumentEditor", options);

        }.bind(this));

        itemNode.getElement(".icon_download").addEvent("click",function(){
            var action = o2.Actions.get("x_onlyoffice_assemble_control");
            var host = action.action.getAddress();
            var path = "/jaxrs/onlyoffice/file/" + this.data.documentId + "/" + data.version + "?xtoken="

            this.srv.execute("getDocumentToken", {
                "documentId": this.data.id
            },function(json) {
                var xtoken = json.fileToken;
                window.open(host + path + xtoken);
            }.bind(this));
        }.bind(this));
        itemNode.getElement(".icon_recycler").addEvent("click",function(){
            this.srv.execute("removeHistory", {
                "documentId": this.data.id,
                "version" : data.version,
            },function(json) {
                this.versionModal.destroy();
                this.history();
            }.bind(this));
        }.bind(this));
        itemNode.getElement(".icon_edit").addEvent("click",function(){

            this.setVersionComment(data);
        }.bind(this));
        // itemNode.getElement(".icon_recover").addEvent("click",function(){
        //     alert("恢复")
        // }.bind(this));
    },
    setVersionComment : function(data){
        this.versionModal.hide();
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);
        var bodyNode = new Element("div");

        var inputNode = new Element("input",{"class":"ant-input"}).inject(bodyNode);
        inputNode.set("value",data.comment);
        var modal = this.wi.modal("版本备注",bodyNode,footerNode);
        cancelBtn.addEvent("click",function(){
            modal.destroy();
            this.versionModal.show();
        }.bind(this));
        okBtn.addEvent("click",function(){

            this.srv.execute("updateDocumentVersion", {
                "documentId" : data.documentId,
                "version" : data.version,
                "comment" : inputNode.get("value")
            },function(json) {
                this.wi.message("success","更新成功");
                modal.destroy();
                this.versionModal.destroy();
                this.history();
            }.bind(this));
        }.bind(this));
    },
    properties : function(){
        this.hideDrop();
        var bodyNode = new Element("div");
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"返回",class:"ant-btn ant-btn-ghost"}).inject(footerNode);

        bodyNode.loadHtml(this.templatePath + "/file_properties.html", { "module": this,"bind": this.data}, function(){
            var modal = this.wi.modal("文件属性",bodyNode,footerNode,{"width":"600px"});
            cancelBtn.addEvent("click",function(){
                modal.destroy();
            }.bind(this));
        }.bind(this));
    },
    onlineSet : function (){
        this.hideDrop();
        var data = this.data;
        o2.loadHtml(this.templatePath + "/file_online.html", function(loaded){
            var html = loaded[0].data;
            var bodyNode = new Element("div",{"html":html});

            var footerNode = new Element("div");
            var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
            var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);
            var modal = this.wi.modal("同时在线打开文档人数设置",bodyNode,footerNode,null,function(){
                this.reload();
            }.bind(this));
            var onlineNode = bodyNode.getElement(".ant-input");
            onlineNode.set("value",data.online);
            var okNode = bodyNode.getElement(".add-btn");
            okBtn.addEvent("click",function(){
                var onlineNum = onlineNode.get("value");

                if (!(/(^[1-9]\d*$)/.test(onlineNum))) {
                    this.wi.message("error","请输入正整数");
                    return ;
                }

                this.srv.execute("setDocumentOnline", {
                    "documentId": data.id,
                    "online": onlineNum
                },function(json) {
                }.bind(this));
                this.wi.message("success","设置成功");
                modal.destroy();
                this.reload();
            }.bind(this));
            cancelBtn.addEvent("click",function(){
                modal.destroy();
            }.bind(this));
        }.bind(this));
    },
    tagSet : function(){
        this.hideDrop();
        var data = this.data;
        o2.loadHtml(this.templatePath + "/file_tag.html", function(loaded){
            var html = loaded[0].data;
            var bodyNode = new Element("div",{"html":html});
            var modal = this.wi.modal("标签设置",bodyNode,null,null,function(){
                this.reload();
            }.bind(this));
            var tagNode = bodyNode.getElement(".ant-select-search__field");

            var tagListNode = bodyNode.getElement(".tags_added");
            new Element("span.tags_added_label",{"text":"已添加的标签："}).inject(tagListNode);

            data.tagList.each(function(tag){
                var node = new Element("span.tags_added_content").inject(tagListNode);
                var textNode = new Element("span",{text:tag}).inject(node);
                var icon = new Element("i",{"class":"iconfont icon_close"}).inject(node);
                icon.addEvent("click",function(){
                    this.srv.execute("removeTag", {
                        "documentId": data.id,
                        "tag": tag
                    },function(json) {
                        node.destroy();
                    }.bind(this));
                }.bind(this));
            }.bind(this));

            var okNode = bodyNode.getElement(".add-btn");
            okNode.addEvent("click",function(){
                tagNode.get("value").split(";").each(function(tag){
                    this.srv.execute("addTag", {
                        "documentId": data.id,
                        "tag": tag
                    },function(json) {

                    }.bind(this));
                }.bind(this));
                this.wi.message("success","设置成功");
                modal.destroy();
                this.reload();
            }.bind(this));
        }.bind(this));
    },
});
