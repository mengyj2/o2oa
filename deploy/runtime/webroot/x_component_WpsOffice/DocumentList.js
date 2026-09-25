MWF.xAction.RestActions.Action["x_wpsfile_assemble_control"] = new Class({
    Extends: MWF.xAction.RestActions.Action
});
MWF.xApplication.WpsOffice.DocumentList = new Class({
    Extends: MWF.widget.Common,
    Implements: [Options, Events],
    options: {
        "style": "default",
        "className" : ""
    },

    initialize: function(node, app, options){
        this.setOptions(options);
        this.app = app;
        this.path = "../x_component_WpsOffice/$Main/" + this.options.style + "/";

        this.css = this.app.css;
        this.lp = this.app.lp;

        this.className = this.options.className;

        this.action = this.app.action;
        this.node = $(node);
    },
    reload: function(){
        this.node.empty();
        this.load();
    },
    load: function(){
        this.node.empty();
        this.createTopNode();
        this.createContainerNode();
        this.setContentSizeFun = this.setContentSize.bind(this);
        this.addEvent("resize", this.setContentSizeFun);
        this.loadView();

        this.app.addEvent("resize", function(){this.setContentSize();}.bind(this));
    },
    loadView: function (filterData) {
        console.log(filterData)
        if (this.view) this.view.destroy();
        this.contentNode.empty();
        var viewContainerNode = this.viewContainerNode = new Element("div.viewContainerNode", {
            "styles": this.css.viewContainerNode
        }).inject(this.contentNode);

        this.view = new MWF.xApplication.WpsOffice[this.className].View(viewContainerNode, this, this, {
            templateUrl: this.path + this.className + "_listItem.json",
            "pagingEnable": true,
            "wrapView": true,
            "noItemText": this.lp.noItem,
            // "scrollType": "window",
            "pagingPar": {
                pagingBarUseWidget: true,
                position: ["bottom"],
                style: "blue_round",
                hasReturn: false,
                currentPage: this.options.viewPageNum,
                countPerPage: 15,
                visiblePages: 9,
                hasNextPage: true,
                hasPrevPage: true,
                hasTruningBar: true,
                hasJumper: true,
                returnText: "",
                hiddenWithDisable: false,
                text: {
                    prePage: "",
                    nextPage: "",
                    firstPage: this.lp.firstPage,
                    lastPage: this.lp.lastPage
                },
                onPostLoad: function () {
                    debugger;
                    this.setContentSize();
                }.bind(this)
            }
        }, {
            lp: this.lp
        });
        if (filterData) this.view.filterData = filterData;
        this.view.load();
    },
    getOffsetY: function (node) {
        return (node.getStyle("margin-top").toInt() || 0) +
            (node.getStyle("margin-bottom").toInt() || 0) +
            (node.getStyle("padding-top").toInt() || 0) +
            (node.getStyle("padding-bottom").toInt() || 0) +
            (node.getStyle("border-top-width").toInt() || 0) +
            (node.getStyle("border-bottom-width").toInt() || 0);
    },
    setContentSize: function () {

        var nodeSize = this.app.node.getSize();
        var h = nodeSize.y - this.getOffsetY(this.node);
        var topY = this.topContainerNode ? (this.getOffsetY(this.topContainerNode) + this.topContainerNode.getSize().y) : 0;
        h = h - topY;
        h = h - this.getOffsetY(this.viewContainerNode);
        h = h - this.getOffsetY(this.app.node);

        var pageSize = (this.view && this.view.pagingContainerBottom) ? this.view.pagingContainerBottom.getComputedSize() : {totalHeight: 0};
        h = h - pageSize.totalHeight;

        this.view.viewWrapNode.setStyles({
            "height": "" + h + "px",
            "overflow": "auto"
        });
    },
    createContainerNode: function () {
        this.createContent();
    },
    createContent: function () {

        this.middleNode = new Element("div.middleNode", {
            "styles": this.css.middleNode
        }).inject(this.node);

        this.contentNode = new Element("div.contentNode", {
            "styles": this.css.contentNode
        }).inject(this.middleNode);

    },
    createTopNode: function () {
        this.topContainerNode = new Element("div.topContainerNode", {
            "styles": this.css.topContainerNode
        }).inject(this.node);

        this.topNode = new Element("div.topNode", {
            "styles": this.css.topNode
        }).inject(this.topContainerNode);

        this.topContentNode = new Element("div", {
            "styles": this.css.topContentNode
        }).inject(this.topNode);

        this.topOperateNode = new Element("div", {
            "styles": this.css.topOperateNode
        }).inject(this.topNode);

        this.loadOperate();
        this.loadFilter();

    },
    loadOperate: function () {
        var lp = MWF.xApplication.WpsOffice.LP;
        this.fileterNode = new Element("div.operateNode", {
            "styles": this.css.fileterNode
        }).inject(this.topOperateNode);

        var html = "<table bordr='0' cellpadding='0' cellspacing='0' styles='filterTable'>" +
            "<tr>" +
            "    <td styles='filterTableValue' item='remove'></td>" +
            "    <td styles='filterTableValue' item='upload'></td>" +
            "</tr>" +
            "</table>";
        this.fileterNode.set("html", html);

        this.fileterForm = new MForm(this.fileterNode, {}, {
            style: "attendance",
            isEdited: true,
            itemTemplate: {
                remove: {
                    "value": "删除", type: "button", className: "filterButtonGrey", event: {
                        click: function (e) {

                            var checkedItems = this.view.getCheckedItems();
                            var _self = this;
                            this.form.app.confirm("warn", e.node, "提示", "您确定要删除吗？", 350, 120, function () {

                                checkedItems.each(function (item){
                                    //item.node.setStyles(item.css.documentNode_remove);
                                    _self.view._remove(item.data);
                                }.bind(this));

                                this.close();
                                _self.form.app.notice("删除成功","success");
                                _self.loadView();

                            }, function () {

                                this.close();
                            });


                        }.bind(this)
                    }
                },
                create: {
                    "value": "创建", type: "button", className: "filterButton", event: {
                        click: function (ev,node) {
                            this.switchTagFor( node.target );
                            node.stopPropagation();
                        }.bind(this)
                    }
                },
                upload: {
                    "value": "上传", type: "button", className: "filterButtonGrey", event: {
                        click: function (e) {


                            this.view._upload();




                        }.bind(this)
                    }
                }
            }
        }, this.app, this.css);
        this.fileterForm.load();
    },
    switchTagFor : function( el ){
        var _self = this;
        var node = this.tagForListNode;
        var parentNode = el;
        if(node){
            if(  node.getStyle("display") == "block" ){
                node.setStyle("display","none");
            }else{
                node.setStyle("display","block");
                node.position({
                    relativeTo: parentNode,
                    position: 'bottomCenter',
                    edge: 'upperCenter'
                });
            }
        }else{
            node = this.tagForListNode = new Element("div",{
                "styles" :  this.css.drownListNode
            }).inject(this.node);
            this.app.content.addEvent("click",function(){
                _self.tagForListNode.setStyle("display","none");
            });

            var actionList = [
                {
                    title : "文档",
                    event : function (e){
                        this.view._create("word");
                        this.loadView();
                    }.bind(this)

                },
                {
                    title : "演示文稿",
                    event : function (e){
                        this.view._create("excel");
                        this.loadView();
                    }.bind(this)

                },
                {
                    title : "表格",
                    event : function (e){
                        this.view._create("ppt");
                        this.loadView();
                    }.bind(this)

                }
            ]
            node.setStyle("margin-left","30px");
            node.setStyle("margin-top","10px");
            actionList.each(function (action){
                var dNode = new Element("div",{
                    "text" : action.title,
                    "styles" : this.css.drownSelectNode,
                }).inject(node);

                dNode.addEvents({
                    "mouseover" : function(){ this.setStyles(_self.css.drownSelectNode_over); },
                    "mouseout" : function(){  this.setStyles(_self.css.drownSelectNode); },
                    "click" : function(e){
                        _self.tagForListNode.setStyle("display","none");
                        this.setStyles(_self.css.drownSelectNode);
                        if(action.event){
                            action.event(e);
                        }
                        e.stopPropagation();
                    }
                })
                node.position({
                    relativeTo: parentNode,
                    position: 'bottomCenter',
                    edge: 'upperCenter'
                });
            }.bind(this));

        }
    },
    loadFilter: function () {
        var lp = MWF.xApplication.WpsOffice.LP;
        this.fileterNode = new Element("div.fileterNode", {
            "styles": this.css.fileterNode
        }).inject(this.topContentNode);

        var html = "<table bordr='0' cellpadding='0' cellspacing='0' styles='filterTable'>" +
            "<tr>" +
            "    <td styles='filterTableTitle' lable='fileName'></td>" +
            "    <td styles='filterTableTitle' item='fileName'></td>" +
            "    <td styles='filterTableTitle' lable='creator'></td>" +
            "    <td styles='filterTableTitle' item='creator'></td>" +
            "    <td styles='filterTableTitle' lable='id'></td>" +
            "    <td styles='filterTableTitle' item='id'></td>" +
            "    <td styles='filterTableTitle' lable='docId'></td>" +
            "    <td styles='filterTableTitle' item='docId'></td>" +
            "    <td styles='filterTableTitle' lable='category'></td>" +
            "    <td styles='filterTableTitle' item='category'></td>" +
            "    <td styles='filterTableValue' item='action'></td>" +
            "    <td styles='filterTableValue' item='reset'></td>" +
            "</tr>" +
            "</table>";
        this.fileterNode.set("html", html);


        this.form = new MForm(this.fileterNode, {}, {
            style: "attendance",
            isEdited: true,
            itemTemplate: {
                fileName: {text: "文件名", "type": "text", "style": {"min-width": "100px"}},
                creator: {
                    "text": "创建人",
                    "type": "org",
                    "orgType": "identity",
                    "orgOptions": {"resultType": "person"},
                    "style": {"min-width": "100px"},
                    "orgWidgetOptions": {"disableInfor": true}
                },
                id: {text: "文档Id", "type": "text", "style": {"min-width": "100px"}},
                docId: {text: "关联Id", "type": "text", "style": {"min-width": "100px"}},
                category: {text: "分类", "type": "text", "style": {"min-width": "100px"}},
                action: {
                    "value": lp.query, type: "button", className: "filterButton", event: {
                        click: function () {
                            var result = this.form.getResult(false, null, false, true, false);
                            for (var key in result) {
                                if (!result[key]) {
                                    delete result[key];
                                } else if (key === "creator" && result[key].length > 0) {
                                    //result[key] = result[key][0].split("@")[1];
                                    result["creator"] = result[key][0];
                                }
                            }
                            this.loadView(result);
                        }.bind(this)
                    }
                },
                reset: {
                    "value": lp.reset, type: "button", className: "filterButtonGrey", event: {
                        click: function () {
                            this.form.reset();
                            this.loadView();
                        }.bind(this)
                    }
                },
            }
        }, this.app, this.css);
        this.form.load();
    },
});
MWF.xApplication.WpsOffice.DocumentList.View = new Class({
    Extends: MWF.xApplication.Template.Explorer.ComplexView,
    _createDocument: function (data, index) {
        return new MWF.xApplication.WpsOffice[this.app.className].Document(this.viewNode, data, this.explorer, this, null, index);
    },
    _getCurrentPageData: function (callback, count, pageNum) {
        this.clearBody();
        if (!count) count = 15;
        if (!pageNum) {
            if (this.pageNum) {
                pageNum = this.pageNum = this.pageNum + 1;
            } else {
                pageNum = this.pageNum = 1;
            }
        } else {
            this.pageNum = pageNum;
        }

        var filter = this.filterData || {};
        //filter.category = "process";

        this.app.action.CustomAction.listPaging(pageNum, count, filter, function (json) {
            if (!json.data) json.data = [];
            if (!json.count) json.count = 0;

            if (callback) callback(json);
        }.bind(this))

    },
    _remove : function (data){
        this.app.action.CustomAction.delete(data.id,function (){},null,false);
    },
    _create: function (type) {
        var extension;
        if(type === "word") extension = "docx";
        if(type === "excel") extension = "xlsx";
        if(type === "ppt") extension = "pptx";

        var dlgNode = new Element("div", {"style": "margin:10px"});
        var fileNameNode = new Element("input", {"style": "width:100%;margin-bottom:5px;height: 30px", "placeholder": "文档名称"}).inject(dlgNode);
        var templateIdNode = new Element("input", {"style": "width:100%;margin-bottom:5px;;height: 30px", "placeholder": "模板id"}).inject(dlgNode);
        var docIdNode = new Element("input", {"style": "width:100%;margin-bottom:5px;;height: 30px", "placeholder": "业务文档id"}).inject(dlgNode);
        var categoryNode = new Element("input", {"style": "width:100%;margin-bottom:5px;;height: 30px", "placeholder": "文档分类"}).inject(dlgNode);

        var fileNameDlg = o2.DL.open({
            "title": "文件名",
            "width": "500px",
            "height": "360px",
            "mask": true,
            "content": dlgNode,
            "container": null,
            "positionNode": this.explorer.app.content,
            "onQueryClose": function () {
                dlgNode.destroy();
            }.bind(this),
            "buttonList": [
                {
                    "text": "确认",
                    "action": function () {

                        var d = {
                            "fileName" : fileNameNode.get("value") + "." + extension,
                            "templateId" : templateIdNode.get("value"),
                            "docId" : docIdNode.get("value"),
                            "category" : categoryNode.get("value")
                        }
                        this.app.action.CustomAction.createFileBlank(type,d,function (json){
                            debugger
                            this.app.loadView();
                            this._edit(json.data);
                        }.bind(this),function (json){

                        },false);

                        fileNameDlg.close();

                    }.bind(this)
                },
                {
                    "text": "关闭",
                    "action": function () {
                        fileNameDlg.close();
                    }.bind(this)
                }
            ],
            "onPostShow": function () {
                fileNameDlg.reCenter();
            }.bind(this)
        });

    },
    _open: function (data) {
        var options = {
            "documentId": data.id,
            "mode":"view",
            "jars" : data.category,
            "appId":  "WpsOfficeEditor" + data.id
        };
        this.app.app.desktop.openApplication(null, "WpsOfficeEditor", options);
    },
    _download: function (data) {

        var uri = new URI(window.location.href);
        var host = uri.get("host")
        var scheme = uri.get("scheme")

        var wpsfile = layout.serviceAddressList["x_wpsfile_assemble_control"];
        var port = wpsfile.port === ""?"" : ":" + wpsfile.port

        window.open(scheme + "://"+ host + port + "/x_wpsfile_assemble_control/jaxrs/wps/download/" + data.id);
    },
    _rename : function (data){
        console.log(data)
        var dlgNode = new Element("div", {"style": "margin:10px"});
        var fileNameNode = new Element("input", {"style": "width:100%;margin-bottom:5px;height: 24px", "value": data.name}).inject(dlgNode);

        var fileNameDlg = o2.DL.open({
            "title": "重命名",
            "width": "300px",
            "height": "160px",
            "mask": true,
            "content": dlgNode,
            "container": null,
            "positionNode": this.explorer.app.content,
            "onQueryClose": function () {
                dlgNode.destroy();
            }.bind(this),
            "buttonList": [
                {
                    "text": "确认",
                    "action": function () {

                        var d = {
                            "fileId" : data.id,
                            "fileName" : fileNameNode.get("value")
                        }
                        this.app.action.CustomAction.rename(d,function (json){
                            this.app.loadView();
                        }.bind(this),function (json){

                        },false);

                        fileNameDlg.close();

                    }.bind(this)
                },
                {
                    "text": "关闭",
                    "action": function () {
                        fileNameDlg.close();
                    }.bind(this)
                }
            ],
            "onPostShow": function () {
                fileNameDlg.reCenter();
            }.bind(this)
        });

    },
    _edit: function (data) {
        var options = {
            "documentId": data.id,
            "mode":"write",
            "jars" : data.category,
            "appId":  "WpsOfficeEditor" + data.id
        };
        this.app.app.desktop.openApplication(null, "WpsOfficeEditor", options);
    },
    _upload : function (){


        o2.Actions.get("x_wpsfile_assemble_control").action.actions = {};
        o2.Actions.get("x_wpsfile_assemble_control").action.actions.upload = {
            "enctype": "formData",
            "method": "POST",
            "uri": "/jaxrs/wps/upload"
        }
        o2.require("o2.widget.Upload", null, false);
        var upload = new o2.widget.Upload(this.app.content, {
            "action": o2.Actions.get("x_wpsfile_assemble_control").action,
            "method": "upload",
            "parameter": {
            },
            "data":{
            },
            "onCompleted": function(){
                this.app.form.app.notice("上传成功","success");
                this.app.loadView();
            }.bind(this)
        });
        upload.load();
    },
    _queryCreateViewNode: function () {

    },
    _postCreateViewNode: function (viewNode) {

    },
    _queryCreateViewHead: function () {

    },
    _postCreateViewHead: function (headNode) {

    }


});
MWF.xApplication.WpsOffice.DocumentList.Document = new Class({
    Extends: MWF.xApplication.Template.Explorer.ComplexDocument,
    mouseoverDocument: function (itemNode, ev) {
        var removeNode = itemNode.getElements("[styles='removeNode']")[0];
        if (removeNode) removeNode.setStyle("opacity", 1)
    },
    mouseoutDocument: function (itemNode, ev) {
        var removeNode = itemNode.getElements("[styles='removeNode']")[0];
        if (removeNode) removeNode.setStyle("opacity", 0)
    },
    _queryCreateDocumentNode: function (itemData) {
    },
    _postCreateDocumentNode: function (itemNode, itemData) {

    },
    open: function () {
        this.view._open(this.data);
    },
    download: function () {
        this.view._download(this.data);
    },
    edit : function (){
        this.view._edit(this.data);
    },
    rename : function (){
        this.view._rename(this.data);
    },
    remove : function (e){

        var _self = this;
        this.node.setStyles(this.css.documentNode_remove);
        this.readyRemove = true;
        this.view.lockNodeStyle = true;

        this.explorer.app.confirm("warn", e, "提示", "确认是否删除", 350, 120, function () {

            _self.view._remove(_self.data);
            _self.view.lockNodeStyle = false;

            this.close();
            _self.view.app.loadView();

        }, function () {
            _self.node.setStyles(_self.css.documentNode);
            _self.readyRemove = false;
            _self.view.lockNodeStyle = false;
            this.close();
        });
    }
});
