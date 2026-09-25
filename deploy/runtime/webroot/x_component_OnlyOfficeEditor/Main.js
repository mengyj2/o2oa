
MWF.xApplication.OnlyOfficeEditor = MWF.xApplication.OnlyOfficeEditor || {};


MWF.xApplication.OnlyOfficeEditor.Main = new Class({
    Extends: MWF.xApplication.Common.Main,
    Implements: [Options, Events],
    options: {
        "style": "default",
        "name": "OnlyOfficeEditor",
        "mvcStyle": "style.css",
        "mode" : "view",
        "jars" : "",
        "title": ""
    },
    onQueryLoad: function () {

        this.lp = MWF.xApplication.OnlyOfficeEditor.LP;
        this.documentId = this.options.documentId;
        this.mode = this.options.mode;
        this.version = this.options.version;
        this.jars = this.options.jars;
        this.action = MWF.Actions.load("x_onlyofficefile_assemble_control");

        if(this.status){
            this.mode = this.status.mode;
            this.documentId = this.status.documentId;
            this.version = this.status.version;
            this.jars = this.status.jars;
        }
        //if(this.jars === "") this.jars = "template";

    },
    onQueryClose : function (){

    },
    loadApplication: function (callback) {

        this.loadDocument();
    },
    loadDocument: function () {
        this.getEditor(function () {
            this.setTitle(this.document.fileName);
            this.loadApi(function (){
                this.loadEditor();
            }.bind(this));
        }.bind(this));
    },
    loadApi : function (callback){
        this.action.OnlyofficeConfigAction.getConfig(function( json ){
            var data = json.data;
            var docserviceApi = data.docserviceApi;
            o2.load(docserviceApi, function () {
                if (callback) callback();
            }.bind(this));
        }.bind(this),null, false);
    },
    getEditor: function (callback) {
        debugger
        if(this.jars === "officeOnline"){

            o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
                "fun" : "getEditor",
                "data" : {
                    "documentId": this.documentId,
                    "version" : this.version,
                    "mode" : this.mode
                }
            },function(json) {

                this.document = json.data;

                if (callback) callback();
            }.bind(this));

        }else if(this.jars === "" || this.jars === undefined){

            this.action.OnlyofficeAction.getEdit(this.documentId,this.mode, function( json ){
                this.document = json.data;
                this.document.editor = this.document.fileModel;
                if (callback) callback();
            }.bind(this),null,false);

        }else {
            this.action.OnlyofficeAction.appFileEdit({
                "appToken" : this.jars,
                "mode" : this.mode,
                "fileId" : this.documentId
            }, function( json ){
                this.document = json.data;
                this.document.editor = this.document.fileModel;
                if (callback) callback();
            }.bind(this),null,false);
        }

    },
    loadEditor : function (){

        var docEditor;
        var _self = this;
        var innerAlert = function (message) {
            if (console && console.log)
                console.log(message);
        };
        var onAppReady = function () {
            innerAlert("Document editor ready");

        };
        var onDocumentStateChange = function (event) {

            var title = document.title.replace(/\*$/g, "");
            document.title = title + (event.data ? "*" : "");
            if(event.data){
                _self.fireEvent("afterSave");
            }
        };
        var onRequestEditRights = function () {
            location.href = location.href.replace(RegExp("mode=view\&?", "i"), "");
        };
        var onRequestHistory = function (event) {
            if (this.document.FileHistory[0] === "") {
                docEditor.refreshHistory({
                    currentVersion: null,
                    history: null
                });
            } else {
                var historyArr = JSON.parse(this.document.FileHistory[0]).history;
                var newHistoryArr = [];
                for (var i = 0; i < historyArr.length; i++) {
                    if (historyArr[i].version > 0) {
                        newHistoryArr.push(historyArr[i]);
                    }
                }
                newHistoryArr.sort(function (a, b) {
                    return a.version - b.version;
                });
                var historyObj = newHistoryArr || null;
                docEditor.refreshHistory({
                    currentVersion: JSON.parse(this.document.FileHistory[0]).currentVersion,
                    history: historyObj
                });
            }
        }.bind(this);
        var onRequestHistoryData = function (data) {
            var historyArr = [];
            var history = JSON.parse(this.document.FileHistory[1]);
            for (var key in history) {
                if (key !== "0") {
                    historyArr.push(history[key]);
                }
            }
            var version = data.data;
            var historyData = historyArr || null;
            docEditor.setHistoryData(historyData[version - 1]);
        }.bind(this);
        var onRequestHistoryClose = function (event) {
            document.location.reload();
        };
        var onError = function (event) {
            if (event) innerAlert(event.data);
        };
        var onOutdatedVersion = function (event) {
            location.reload(true);
        };
        var onDocumentReady= function() {
            console.log("Document is loaded");
            this.fireEvent("afterOpen");
        }.bind(this);

        this.document.editor.events = {
            "onAppReady": onAppReady,
            "onDocumentReady":onDocumentReady,
            "onDocumentStateChange": onDocumentStateChange,
            'onRequestEditRights': onRequestEditRights,
            "onError": onError,
            "onOutdatedVersion": onOutdatedVersion,
        }

        if(this.document.FileHistory){
            if (this.document.FileHistory[0] !== "") {
                this.document.editor.events.onRequestHistory = onRequestHistory;
                this.document.editor.events.onRequestHistoryData = onRequestHistoryData;
                this.document.editor.events.onRequestHistoryClose = onRequestHistoryClose;
            }
        }


        //this.document.editor.editorConfig.mode = this.mode;
        if(layout.mobile){
            this.document.editor.type = "mobile";
        }
        this.officeNode = new Element("div#_" + this.documentId).inject(this.content);
        console.log(this.document.editor)
        docEditor = new DocsAPI.DocEditor("_" + this.documentId, this.document.editor);
        this.onlyOffice = docEditor;
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
