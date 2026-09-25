
o2.xApplication.CloudDocument.ShareToMeExplorer = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer,
    initData : function (){
        this.srv.execute("queryShareToMeByPage", {
            "page" : this.page,
            "pageSize" : this.pageSize
        },function(json) {
            json.dataList.each(function(d){
                d.name = d.fileName;
            }.bind(this));
            this.dataList = json.dataList;
            this._initData();
        }.bind(this));
    },
    loadBread : function (){
        this.breadNode.empty();
        var breadNode = new Element("div.root_share").inject(this.breadNode);
        var shareToMeMenu = new Element("a",{text:"我收到的"}).inject(breadNode).addEvent("click",function(){
            this.app.loadShareToMe();
        }.bind(this));
        new Element("span.separator",{"text":"|"}).inject(breadNode);
        var myShareMenu = new Element("a",{text:"我发出的"}).inject(breadNode).addEvent("click",function(){
            this.app.loadMyShare();
        }.bind(this));
        shareToMeMenu.addClass("active");
    },
});
o2.xApplication.CloudDocument.ShareToMeExplorer.View = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer.View

});
o2.xApplication.CloudDocument.ShareToMeExplorer.Document = new Class({
    Extends: o2.xApplication.CloudDocument.Explorer.Document
});
