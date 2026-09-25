MWF.xApplication.WpsOffice.Setting = new Class({
    Extends: MPopupForm,
    Implements: [Options, Events],
    options: {
        "style": "attendanceV2",
        "width": "800",
        "height": "500",
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
                appId: {"text": "wps接入应用ID", "type": "text","style": {"width": "90%"}},
                appSecret: {"text": "wps接入应用秘钥", "type": "text","style": {"width": "90%"}},
                host: {"text": "wps服务地址.", "type": "text","style": {"width": "90%"}},
                version: {"text": "接入wps版本", "type": "radio","selectValue":"wpsWebOffice,wpsMiddlePlatform","selectText":"公网版本,私有化部署版本"},
                downloadUrl: {"text": "wps下载附件服务地址", "type": "text","style": {"width": "90%"}},

            },
            onPostLoad:function(){

            }.bind(this)
        },this.app,this.css);
        this.form.load();

    },

    getHtml : function(){
        return  "<table width='100%' bordr='0' cellpadding='0' cellspacing='0' styles='formTable'>" +

            "<tr ><td styles='formTableTitleRight' lable='appId' width='200px'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='appId'></div>" +
            "   </td>" +
            "</tr>" +

            "<tr ><td styles='formTableTitleRight' lable='appSecret'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='appSecret'></div>" +
            "   </td>" +
            "</tr>" +
            "<tr ><td styles='formTableTitleRight' lable='host'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='host'></div>" +
            "   </td>" +
            "</tr>" +
            "<tr ><td styles='formTableTitleRight' lable='version'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='version'></div>" +
            "   </td>" +
            "</tr>" +
            "<tr ><td styles='formTableTitleRight' lable='downloadUrl'></td>" +
            "    <td styles='formTableValue' colspan='2'>" +
            "       <div item='downloadUrl'></div>" +
            "   </td>" +
            "</tr>" +


            "</table>";
    },
    _ok: function (data, callback) {

        this.app.action.ConfigAction.saveConfig(data,function (){
            this.app.notice("创建成功","success");
            this.close();
        }.bind(this),null,false);
    },
});
