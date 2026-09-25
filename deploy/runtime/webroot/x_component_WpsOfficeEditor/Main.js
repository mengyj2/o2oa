
MWF.xApplication.WpsOfficeEditor = MWF.xApplication.WpsOfficeEditor || {};


MWF.xApplication.WpsOfficeEditor.Main = new Class({
    Extends: MWF.xApplication.Common.Main,
    Implements: [Options, Events],
    options: {
        "style": "default",
        "name": "WpsOfficeEditor",
        "mvcStyle": "style.css",
        "mode" : "view",
        "title": ""
    },
    onQueryLoad: function () {

        this.lp = MWF.xApplication.WpsOfficeEditor.LP;
        this.documentId = this.options.documentId;
        this.mode = this.options.mode;
        this.version = this.options.version;
        this.jars = this.options.jars;
        this.action = MWF.Actions.load("x_wpsfile_assemble_control");

        this.officeType = {
            "docx" : "Writer",
            "doc" : "Writer",
            "xlsx" : "Spreadsheet",
            "xls" : "Spreadsheet",
            "pptx" : "Presentation",
            "ppt" : "Presentation",
            "pdf" : "Pdf"
        }

        if(this.status){
            this.jars = this.status.jars;
            this.mode = this.status.mode;
            this.documentId = this.status.documentId;
            this.version = this.status.version;
        }

    },
    onQueryClose : function (){

    },
    loadApplication: function (callback) {
        this.getDocument(function (){
            this.loadDocument();
        }.bind(this))

    },
    loadDocument: function () {


        this.getEditor(function () {

            this.setTitle(this.documentData.name);
            this.loadApi(function (){
                this.loadEditor();
            }.bind(this));
        }.bind(this));
    },
    getDocument: function (callback) {
        debugger
        if(this.jars === "x_processplatform_assemble_surface"){

            o2.Actions.load("x_processplatform_assemble_surface").AttachmentAction.getOnlineInfo(this.documentId,function(json) {

                this.documentData = json.data;

                if (callback) callback();
            }.bind(this));

        }else if(this.jars === "x_cms_assemble_control"){

            o2.Actions.load("x_cms_assemble_control").FileInfoAction.getOnlineInfo(this.documentId,function(json) {

                this.documentData = json.data;

                if (callback) callback();
            }.bind(this));

        }else {
            this.action.CustomAction.getInfo(this.documentId,function( json ){
                this.documentData = json.data;

                if (callback) callback();
            }.bind(this),null,false);
        }

    },
    loadApi : function (callback){

        o2.load(["../x_component_WpsOfficeEditor/web-office-sdk-solution-v2.0.2.umd.min.js"], {"sequence": true}, function () {
            if (callback) callback();
        }.bind(this));
    },
    getEditor: function (callback) {

        this.action.ConfigAction.getAppId(function( json ){
            this.appId = json.data.value;
            if (callback) callback();
        }.bind(this),null,false);
    },
    loadEditor : function (){

        this.wpsOffice = WebOfficeSDK.init({
            officeType: WebOfficeSDK.OfficeType[this.officeType[this.documentData.extension.toLowerCase()]],
            appId: this.appId,
            fileId: this.documentId.replace(/-/g, "_"),
            token: layout.session.token,
            customArgs : {
                "appToken" : this.jars,
                "mode" : this.mode
            },
            mount: this.content
        })

    },
    recordStatus: function(){
        var status ={
            "documentId": this.documentId,
            "mode": this.mode,
            "jars" : this.jars
        };
        return status;
    },
});
