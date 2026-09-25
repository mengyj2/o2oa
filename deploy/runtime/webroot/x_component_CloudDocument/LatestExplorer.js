
o2.xApplication.CloudDocument.LatestExplorer = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer,
    initData : function (){
        this.srv.execute("queryLatestByPage", {
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
        this._loadBread("最近浏览");
    },
    _loadBread : function (name){
        this.breadNode.empty();
        var breadNode = new Element("span").inject(this.breadNode);
        var linkNode = new Element("span.ant-breadcrumb-link").inject(breadNode);
        linkNode.set("html",'<a href="javascript:;">'+ name +'</a>');
    },
});
o2.xApplication.CloudDocument.LatestExplorer.View = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer.View

});
o2.xApplication.CloudDocument.LatestExplorer.Document = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer.Document
});
