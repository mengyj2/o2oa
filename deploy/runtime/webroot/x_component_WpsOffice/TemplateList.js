MWF.xDesktop.requireApp("WpsOffice", "DocumentList", null,false);
MWF.xApplication.WpsOffice.TemplateList = new Class({
    Extends: MWF.xApplication.WpsOffice.DocumentList
});
MWF.xApplication.WpsOffice.TemplateList.View = new Class({
    Extends: MWF.xApplication.WpsOffice.DocumentList.View,
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
        filter.category = "template";

        this.app.action.CustomAction.listPaging(pageNum, count, filter, function (json) {
            if (!json.data) json.data = [];
            if (!json.count) json.count = 0;

            if (callback) callback(json);
        }.bind(this))

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
                "category" : "template"
            },
            "onCompleted": function(){
                this.app.form.app.notice("上传成功","success");
                this.app.loadView();
            }.bind(this)
        });
        upload.load();
    },
});
MWF.xApplication.WpsOffice.TemplateList.Document = new Class({
    Extends: MWF.xApplication.WpsOffice.DocumentList.Document,
});
