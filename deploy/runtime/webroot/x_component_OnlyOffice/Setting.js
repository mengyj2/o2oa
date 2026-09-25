MWF.xApplication.OnlyOffice.Setting = new Class({
    Extends: MPopupForm,
    Implements: [Options, Events],
    options: {
        "style": "attendanceV2",
        "width": "800",
        "height": "600",
        "hasTop": true,
        "hasIcon": false,
        "hasTopIcon" : false,
        "hasTopContent" : false,
        "draggable": true,
        "maxAction" : true,
        "resizeable" : true,
        "closeAction": true,
        "title": "编辑配置文件",
        "closeByClickMaskWhenReading": true,
        "hasBottom" : true,
        "buttonList" : [{ "type":"ok", "text": "保存" },{ "type":"cancel", "text": "取消" }]
    },
    onQueryOpen : function (){

    },
    _postLoad: function(){
        this._createTableContent_();
    },
    _createTableContent: function(){},
    _createTableContent_: function () {

        this.formTableArea.set("html", this.getHtml());

        this.form = new MForm(this.formTableArea, this.data, {
            isEdited: true,
            style : "attendance",
            itemTemplate: {
                filesizeMax: {"text": "最大文件大小", "type": "text","style": {"width": "90%"}},
                timeout: {"text": "超时时间", "type": "text","style": {"width": "90%"}},
                docserviceViewedDocs: {"text": "查看文件类型", "type": "text","style": {"width": "90%"}},
                docserviceEditedDocs: {"text": "编辑文件类型", "type": "text","style": {"width": "90%"}},
                docserviceConvertDocs: {"text": "转换文件类型", "type": "text","style": {"width": "90%"}},
                docserviceConverter: {"text": "转换地址", "type": "text","style": {"width": "90%"}},
                docserviceTempstorage: {"text": "临时存储路径", "type": "text","style": {"width": "90%"}},
                docserviceApi: {"text": "前端api地址", "type": "text","style": {"width": "90%"}},
                docservicePreloader: {"text": "前端刷新地址", "type": "text","style": {"width": "90%"}},
                downLoadUrl: {"text": "OnlyOffice访问O2地址", "type": "text","style": {"width": "90%"}},
                secret: {"text": "密钥", "type": "text","style": {"width": "90%"}},
                ipWhiteList: {"text": "文件下载允许ip", "type": "text","style": {"width": "90%"}},
                gobackUrl: {"text": "回退地址", "type": "text","style": {"width": "90%"}},

            },
            onPostLoad:function(){

            }.bind(this)
        },this.app,this.css);
        this.form.load();

    },

    getHtml : function(){
        return  "<table width='100%' bordr='0' cellpadding='0' cellspacing='0' styles='formTable'>" +

            "<tr ><td styles='formTableTitleRight' lable='filesizeMax'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='filesizeMax'></div>" +
            "   </td>" +
            "</tr>" +

            "<tr ><td styles='formTableTitleRight' lable='timeout'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='timeout'></div>" +
            "   </td>" +
            "</tr>" +

            "<tr ><td styles='formTableTitleRight' lable='docserviceViewedDocs'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='docserviceViewedDocs'></div>" +
            "   </td>" +
            "</tr>" +

            "<tr ><td styles='formTableTitleRight' lable='docserviceEditedDocs'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='docserviceEditedDocs'></div>" +
            "   </td>" +
            "</tr>" +
            "<tr ><td styles='formTableTitleRight' lable='docserviceConvertDocs'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='docserviceConvertDocs'></div>" +
            "   </td>" +
            "</tr>" +
            "<tr ><td styles='formTableTitleRight' lable='docserviceConverter'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='docserviceConverter'></div>" +
            "   </td>" +
            "</tr>" +
            "<tr ><td styles='formTableTitleRight' lable='docserviceTempstorage'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='docserviceTempstorage'></div>" +
            "   </td>" +
            "</tr>" +
            "<tr ><td styles='formTableTitleRight' lable='docserviceApi'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='docserviceApi'></div>" +
            "   </td>" +
            "</tr>" +
            "<tr ><td styles='formTableTitleRight' lable='docservicePreloader'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='docservicePreloader'></div>" +
            "   </td>" +
            "</tr>" +
            "<tr ><td styles='formTableTitleRight' lable='secret'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='secret'></div>" +
            "   </td>" +
            "</tr>" +
            "<tr ><td styles='formTableTitleRight' lable='downLoadUrl'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='downLoadUrl'></div>" +
            "   </td>" +
            "</tr>" +


            "<tr ><td styles='formTableTitleRight' lable='ipWhiteList'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='ipWhiteList'></div>" +
            "   </td>" +
            "</tr>" +
            "</table>";
    },
    _ok: function (data, callback) {

        this.app.action.OnlyofficeConfigAction.saveConfig(data,function (){
            this.app.notice("创建成功","success");
            this.close();
        }.bind(this),null,false);
    },
});
