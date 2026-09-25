o2.xApplication.CloudDocument.SearchExplorer = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer,
    initData : function (){
        this.searchKey = this.options.searchKey;
        this.menuType = "search";
        var dataList = [];
        var data = {
            "page" : this.options.page,
            "pageSize" : this.options.pageSize,
        };
        if(this.searchKey !==""){
            data.key = this.searchKey;
        }
        this.srv.execute("queryDocumentByPage", data,function(json) {
            dataList = json.dataList;
            dataList.each(function(d){
                d.name = d.fileName;
            });
            this.dataList = json.dataList;
            this._initData();
        }.bind(this));

    },
    loadBread : function (){
        this._loadBread(this.searchKey);
    },
    _loadBread : function (key){
        this.breadNode.empty();
        var breadNode = new Element("div.root_search").inject(this.breadNode);
        new Element("a.root_search_actions",{
            html:'<i class="iconfont icon_back "></i><span>返回</span>'
        }).inject(breadNode).addEvent("click",function(){
            this.app.cancelSearch();
        }.bind(this));
        new Element("div.root_search_value",{
            "html":'<div class="title">关键字：<span class="value">'+ key +'</span></div>'
        }).inject(breadNode);
    },
});
o2.xApplication.CloudDocument.SearchExplorer.View = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer.View

});
o2.xApplication.CloudDocument.SearchExplorer.Document = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer.Document
});
