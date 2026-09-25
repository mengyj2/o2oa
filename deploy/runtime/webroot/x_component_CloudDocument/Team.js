o2.xApplication.CloudDocument.Team = new Class({
    Implements: [Options, Events],
    options: {

    },
    initialize: function (app, data, teamNode,options) {

        this.setOptions(options);
        this.app = app;
        this.wi = this.app.wi;
        this.data = data;
        this.teamMenuNode = teamNode;

    },
    setAcl : function(){
        this.app.newDropNode.destroy();

        this.teamAclNode = new Element("div");
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);
        this.teamAclNode.loadHtml(this.app.path + this.app.options.style + "/team_acl.html", { "module": this,"bind": {"lp": this.lp,"data":this.data}}, function(){
            this.teamAclModal = this.wi.modal("根目录权限设置",this.teamAclNode,footerNode,{"width":"820px"});

            okBtn.addEvent("click",function(){
                this.teamAclModal.destroy();
            }.bind(this));

            cancelBtn.addEvent("click",function(){
                this.teamAclModal.destroy();
            }.bind(this));
        }.bind(this));
    },
    teamSet : function(){

        this.app.newDropNode.destroy();

        this.teamSetNode = new Element("div");
        this.teamSetNode.loadHtml(this.app.path + this.app.options.style + "/team_set.html", { "module": this,"bind": {"lp": this.lp,"data":this.data}}, function(){
            this.teamSetModal = this.wi.modal(null,this.teamSetNode,null,{"width":"640px"});
            var ink = this.teamSetNode.getElement(".ant-tabs-ink-bar");
            var tabpaneList = this.teamSetNode.getElements(".ant-tabs-tabpane");
            var tabContent = this.teamSetNode.getElement(".ant-tabs-content");
            this.teamSetNode.getElements(".ant-tabs-tab").each(function(tab,index){
                tab.addEvent("click",function(ev){
                    tab.getSiblings().removeClass("ant-tabs-tab-active");
                    tab.addClass("ant-tabs-tab-active");
                    ink.setStyle("transform","translate3d("+ (index*142) +"px, 0px, 0px)");
                    tabpaneList.set("class","ant-tabs-tabpane ant-tabs-tabpane-inactive");
                    tabpaneList[index].set("class","ant-tabs-tabpane ant-tabs-tabpane-active");

                    tabContent.setStyle("margin-left","-"+(index*100)+"%");
                }.bind(this));
            }.bind(this));

            this.loadTeamPersonList();
        }.bind(this));
    },
    loadTeamPersonList : function(){
        this.teamPersonListNode.empty();
        this.app.srv.execute("getDocumentAcl", {documentId:this.data.id},function(json) {
            o2.loadHtml(this.app.path + this.app.options.style + "/team_person.html", function(loaded){
                var html = loaded[0].data;
                json.each(function(data){
                    this.loadTeamPersonItem(data,html);
                }.bind(this));

            }.bind(this));
        }.bind(this));
    },
    loadTeamPersonItem : function(data,html){
        data.userImg = this.app.util.getAvatar(data.person.split("@")[1]);
        data.userName = data.person.split("@")[0];
        data.aclName = this.app.util.getAclName(data.acl);

        html = html.bindJson(data);
        var tmpNode = new Element("tbody",{"html":html});

        var itemNode = tmpNode.getFirst().inject(this.teamPersonListNode);
        itemNode.getElement(".acl").addEvent("click",function(ev){
            if(data.acl>0) this.setPersonAcl(ev,data);
        }.bind(this));

        // o2.injectHtml(html,{
        //     "bind": data,
        //     "module": this,
        //     "dom": this.teamPersonListNode,
        //     "position": "beforeend"
        // });
    },
    setPersonAcl : function(ev,data){
        var bodyNode = new Element("div");
        bodyNode.loadHtml(this.app.path + this.app.options.style + "/team_person_acl.html", { "module": this,"bind": {"lp": this.lp,"user":this.user}}, function(){
            this.newDropNode = this.wi.dropdown(ev,bodyNode);
            this.newDropNode.getElements("a").addEvent("click",function(ev){
                var role = ev.target.get("role");
                if(role==="remove"){
                    this.removeAcl(data.person);
                }else{
                    this.updateAcl(data.person,role);
                }
            }.bind(this));
        }.bind(this));
    },
    updateAcl : function(person,acl){
        this.app.srv.execute("updateAcl", {
            documentId : this.data.id,
            aclPerson : person,
            acl : acl
        },function(json) {
            this.loadTeamPersonList();
            this.newDropNode.destroy();
        }.bind(this));
    },
    removeAcl : function(person){
        this.app.srv.execute("removeAcl", {
            documentId : this.data.id,
            aclPerson : person
        },function(json) {
            this.loadTeamPersonList();
            this.newDropNode.destroy();
        }.bind(this));
    },
    setIcon : function(){
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);
        var bodyNode = new Element("div");
        bodyNode.loadHtml(this.app.path + this.app.options.style + "/team_icon.html", { "module": this,"bind": {"lp": this.lp,"data":this.data}}, function(){
            var modal = this.wi.modal("设置团队图标",bodyNode,footerNode);
            cancelBtn.addEvent("click",function(){
                modal.destroy();
            }.bind(this));
            bodyNode.getElements(".teamIcon").addEvent("click",function(ev){
                if(bodyNode.getElement(".teamIconCheck")){
                    bodyNode.getElement(".teamIconCheck").destroy();
                }
                new Element("div",{"class":"teamIconCheck","html":'<i class="iconfont icon_check check"></i>'}).inject(ev.target);
            });
            okBtn.addEvent("click",function(){
                this.data.icon = bodyNode.getElement(".teamIconCheck").getParent().get("icon");
                this.app.srv.execute("updateTeam", this.data,function(json) {
                    this.wi.message("success","更新成功");
                    this.teamMenuNode.getElement("img").set("src","/m_app/cloudDocument/img/team/" + this.data.icon + ".png");
                    this.teamIconNode.setStyle("background-image","url(/m_app/cloudDocument/img/team/"+this.data.icon+".png");
                    modal.destroy();
                }.bind(this));
            }.bind(this));
        }.bind(this));
    },
    setDesc : function(){
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);
        var bodyNode = new Element("div");
        bodyNode.loadHtml(this.app.path + this.app.options.style + "/team_desc.html", { "module": this,"bind": {"lp": this.lp,"data":this.data}}, function(){
            var modal = this.wi.modal("团队公告",bodyNode,footerNode);
            cancelBtn.addEvent("click",function(){
                modal.destroy();
            }.bind(this));
            okBtn.addEvent("click",function(){
                this.data.desc = bodyNode.getElement("textarea").get("value");
                this.app.srv.execute("updateTeam", this.data,function(json) {
                    this.wi.message("success","更新成功");
                    this.teamDescNode.set("text",this.data.desc);
                    modal.destroy();
                }.bind(this));
            }.bind(this));
        }.bind(this));
    },
    setName : function(){
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);
        var bodyNode = new Element("div");
        bodyNode.loadHtml(this.app.path + this.app.options.style + "/team_name.html", { "module": this,"bind": {"lp": this.lp,"data":this.data}}, function(){
            var modal = this.wi.modal("团队名称",bodyNode,footerNode);
            cancelBtn.addEvent("click",function(){
                modal.destroy();
            }.bind(this));
            okBtn.addEvent("click",function(){
                this.data.name = bodyNode.getElement("input").get("value");
                this.app.srv.execute("updateTeam", this.data,function(json) {
                    this.wi.message("success","更新成功");
                    this.teamEditNameNode.set("text",this.data.name);
                    this.teamMenuNode.getElement(".team-text").set("text",this.data.name);
                    modal.destroy();
                }.bind(this));
            }.bind(this));
        }.bind(this));
    },
    addPerson : function(){
        var opt = {
            "types": ["identity"],
            "count": 0,
            "title": "添加成员",
            "values":[],
            "onComplete": function (items) {
                var dataList = [];
                items.each(function(item){
                    dataList.push({
                        person : item.data.woPerson.distinguishedName,
                        acl : 2
                    })
                })
                this.app.srv.execute("addAcl", {
                    documentId : this.data.id,
                    dataList : dataList
                },function(json) {
                    this.loadTeamPersonList();
                }.bind(this));
            }.bind(this)
        };
        o2.xDesktop.requireApp("Selector", "package", function(){
            new o2.O2Selector(this.app.app.page.getApp().node, opt);
        }.bind(this), false);
    },
    setTop : function(){
        this.data.top = true;
        this.app.srv.execute("updateTeam", this.data,function(json) {
            this.wi.message("success","置顶成功");
            this.app.loadTeamList();
            this.app.newDropNode.destroy();
        }.bind(this));
    },
    unTop : function(){
        this.data.top = false;
        this.app.srv.execute("updateTeam", this.data,function(json) {
            this.wi.message("success","取消置顶成功");
            this.app.loadTeamList();
            this.app.newDropNode.destroy();
        }.bind(this));
    },
    recycle : function(){
        this.app.loadTeamRecycle(this.data);
    },
    versionSet : function(){
        var footerNode = new Element("div");
        var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
        var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);
        var bodyNode = new Element("div");

        var inputNode = new Element("input",{"class":"ant-input"}).inject(bodyNode);
        inputNode.set("value",this.data.version);
        var modal = this.wi.modal("历史版本保存数量",bodyNode,footerNode);
        cancelBtn.addEvent("click",function(){
            modal.destroy();
        }.bind(this));
        okBtn.addEvent("click",function(){
            this.data.version = inputNode.get("value");
            this.app.srv.execute("updateTeam", this.data,function(json) {
                this.wi.message("success","更新成功");
                this.teamVersionNode.set("text",this.data.version);
                modal.destroy();
            }.bind(this));
        }.bind(this));


    },
    removeTeam : function(ev){
        this.wi.popConfirm(ev,"您确定要删除？",function(){
            this.app.srv.execute("removeTeam", {
                "teamId": this.data.id,
            },function(json) {
                this.wi.message("success","删除成功");
                this.app.loadTeamList();
                this.teamSetModal.destroy();
            }.bind(this));
        }.bind(this));
    },
});