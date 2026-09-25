
o2.xApplication.CloudDocument.FavExplorer = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer,
    initData : function (){
        this.srv.execute("queryFavByPage", {
            "page" : this.options.page,
            "pageSize" : this.options.pageSize
        },function(json) {
            json.dataList.each(function(d){
                d.name = d.fileName;
            }.bind(this));
            this.dataList = json.dataList;
            this._initData();
        }.bind(this));

    },
    loadBread : function (){
        this._loadBread("星标文档");
    },
    _loadBread : function (name){
        this.breadNode.empty();
        var breadNode = new Element("span").inject(this.breadNode);
        var linkNode = new Element("span.ant-breadcrumb-link").inject(breadNode);
        linkNode.set("html",'<a href="javascript:;">'+ name +'</a>');
    },
});
o2.xApplication.CloudDocument.FavExplorer.View = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer.View,
    unStarMulti : function(){
        var fileList = this.getSelected();
        fileList.each(function(data){
            this.srv.execute("deleteFav", {
                "documentId": data.id
            },function(json) {

            }.bind(this));
        }.bind(this));
        this.wi.message("success","取消成功");
        this.reload();
        this.cancelAll();
    },
});
o2.xApplication.CloudDocument.FavExplorer.Document = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer.Document
});
