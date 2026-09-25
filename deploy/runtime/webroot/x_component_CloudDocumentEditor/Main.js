o2.requireApp("CloudDocument", "Common", null, false);
o2.xApplication.CloudDocumentEditor.Main = new Class({
    Extends: o2.xApplication.Common.Main,
    Implements: [Options, Events],
    options: {
        "style": "default",
        "name": "CloudDocumentEditor",
        "mvcStyle": "style.css",
        "title": o2.xApplication.CloudDocumentEditor.LP.title
    },
    onQueryLoad: function () {
        this.lp = o2.xApplication.CloudDocumentEditor.LP;
        this.documentId = this.options.documentId;
        this.mode = this.options.mode;
        this.version = this.options.version;
        this.srv = new o2.xApplication.CloudDocument.Service();
    },
    onQueryClose : function (){

    },
    loadApplication: function (callback) {
        this.loadDocument();
    },
    loadDocument: function () {
        this.getEditor(function () {
            this.setTitle(this.document.editor.document.title);

            this.loadApi(function (){
                this.srv.do("cloudDocumentSrv", "addDocumentOnline", {
                    "documentId": this.documentId
                }, function (json) {
                    this.loadEditor();
                }.bind(this));
            }.bind(this));
        }.bind(this));
    },
    loadApi : function (callback){
        o2.load(this.document.docserviceApi, function () {
            if(!DocsAPI){
                this.loadApi(callback);
            }else {
                if (callback) callback();
            }
        }.bind(this))
    },
    getEditor: function (callback) {
        this.srv.do("cloudDocumentSrv", "getEditor", {
            "documentId": this.documentId,
            "version" : this.version,
            "mode" : this.mode
        }, function (json) {
            this.document = json;
            if (callback) callback();
        }.bind(this));
    },
    loadEditor: function () {
        var docEditor;
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
            var _this = this;
            setTimeout(function (){
                debugger;
                var historyObj = null;
                if(_this.document.FileHistory[0]==="") {
                    docEditor.refreshHistory(
                        {
                            currentVersion: null,
                            history: null
                        });
                }else{
                    var historyArr = JSON.parse(_this.document.FileHistory[0]).history;
                    var newHistoryArr = [];
                    for(var i = 0 ; i < historyArr.length ; i ++){
                        if(historyArr[i].version > 0){
                            newHistoryArr.push(historyArr[i]);
                        }
                    }
                    newHistoryArr.sort(function(a, b){
                        return a.version - b.version;
                    });

                    historyObj = newHistoryArr || null;
                }
                docEditor.refreshHistory(
                    {
                        currentVersion: _this.version,
                        history: historyObj
                    });
            }, 300);
        }.bind(this);
        var connectEditor = function () {

            this.document.editor.events = {
                "onAppReady": onAppReady,
                "onDocumentStateChange": onDocumentStateChange,
                'onRequestEditRights': onRequestEditRights,
                "onError": onError,
                "onOutdatedVersion": onOutdatedVersion,
            }
            if (this.document.FileHistory[0] !== "") {
                this.document.editor.events.onRequestHistory = onRequestHistory;
                this.document.editor.events.onRequestHistoryData = onRequestHistoryData;
                this.document.editor.events.onRequestHistoryClose = onRequestHistoryClose;
            }
            if(layout.mobile){
                this.document.editor.type = "mobile";
                this.document.editor.editorConfig.customization.goback.url = "http://doc.o2oa.net/x_desktop/documentMobile.html?app=CloudDocumentMobile&debugger"
            }
            // this.document.editor.editorConfig.plugins= {
            //     "autostart": [
            //         "asc.{CF3A000F-C6B4-451D-AC0B-F3DDAB1880D3}"
            //     ],
            //     "pluginsData": [
            //         "http://document.o2oa.net/sdkjs-plugins/watermark/config.json"
            //     ]
            // }
            //打开历史版本
            if(this.version){
                this.document.editor.events.onDocumentReady =  onDocumentReady
            }
            this.document.editor.document.url = o2.filterUrl(this.document.editor.document.url);
            this.document.editor.editorConfig.callbackUrl = o2.filterUrl(this.document.editor.editorConfig.callbackUrl);
            docEditor = new DocsAPI.DocEditor("appContent", this.document.editor);

            fixSize();

        }.bind(this);
        var fixSize = function () {
            var wrapEl = document.getElementsByClassName("form");
            if (wrapEl.length) {
                wrapEl[0].style.height = screen.availHeight + "px";
                window.scrollTo(0, -1);
                wrapEl[0].style.height = window.innerHeight + "px";
            }
        }.bind(this);
        connectEditor();
    }
});
