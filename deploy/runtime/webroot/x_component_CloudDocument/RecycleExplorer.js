
o2.xApplication.CloudDocument.RecycleExplorer = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer,
    initData : function (){
        this.dataList = [];
        var folderList = this.getFolderList(this.folderId,true);

        folderList.each(function(data){
            this.dataList.push(data);
        }.bind(this));


        this.srv.execute("queryDocumentByPage", {
            "page" : this.page,
            "pageSize" : this.pageSize,
            "isRemove" : true
        },function(json) {
            json.dataList.each(function(d){
                d.name = d.fileName;
                this.dataList.push(d);
            }.bind(this));
            this._initData();
        }.bind(this));

    },
    loadBread : function (){
        this._loadBread("回收站");
    },
    _loadBread : function (name){
        this.breadNode.empty();
        var breadNode = new Element("span").inject(this.breadNode);
        var linkNode = new Element("span.ant-breadcrumb-link").inject(breadNode);
        linkNode.set("html",'<a href="javascript:;">'+ name +'</a>');
    },
});
o2.xApplication.CloudDocument.RecycleExplorer.View = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer.View,
    resumeMulti : function(){
        var fileList = this.getSelected();
        var tip;
        if(fileList.length===1) tip = '恢复文件“'+ fileList[0].name +'”？';
        if(fileList.length>1) tip = '恢复选中的 '+ fileList.length +' 个文件(夹)？';
        this.wi.confirm("恢复文件",tip,null,function(){
            fileList.each(function(data){
                this.srv.execute(data.fileType==="folder"?"resumeFolder":"resumeDocument", {
                    "documentId": data.id,
                    "folderId" : data.id,
                },function(json) {

                }.bind(this));
            }.bind(this));

            this.wi.message("success","恢复成功");
            this.reload();
            this.cancelAll();
        }.bind(this));
    },
    shiftRemoveMulti : function(){
        var fileList = this.getSelected();
        var tip;
        if(fileList.length===1) tip = '彻底删除文件“'+ fileList[0].name +'”？';
        if(fileList.length>1) tip = '彻底删除选中的 '+ fileList.length +' 个文件(夹)？';
        this.wi.confirm("彻底删除文件",tip,null,function(){
            fileList.each(function(data){
                this.srv.execute(data.fileType==="folder"?"removeFolder":"removeDocument", {
                    "documentId": data.id,
                    "folderId" : data.id,
                    "soft" :false
                },function(json) {

                }.bind(this));
            }.bind(this));

            this.wi.message("success","删除成功");
            this.reload();
        }.bind(this));

    },

});
o2.xApplication.CloudDocument.RecycleExplorer.Document = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer.Document,
    resume :function () {
        this.hideDrop();
        var data = this.data;
        var tip = '恢复文件“'+ data.name +'”？';
        this.wi.confirm("恢复文件",tip,null,function(){
            this.srv.execute(data.fileType==="folder"?"resumeFolder":"resumeDocument", {
                "documentId": data.id,
                "folderId" : data.id,
            },function(json) {
                this.wi.message("success","恢复成功");
                this.reload();
            }.bind(this));
        }.bind(this));
    },
    shiftRemove:function () {
        this.hideDrop();
        var data = this.data;
        var tip;
        tip = '彻底删除“'+ data.name +'”？'
        this.wi.confirm("彻底删除文件",tip,null,function(){
            this.srv.execute(data.fileType==="folder"?"removeFolder":"removeDocument", {
                "documentId": data.id,
                "folderId" : data.id,
                "soft" :false
            },function(json) {
                this.wi.message("success","删除成功");
                this.reload();
            }.bind(this));
        }.bind(this));
    }
});
