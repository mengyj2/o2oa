o2.xApplication.CloudDocument.User = new Class({
    Implements: [Options, Events],
    options: {
        "style": "default"
    },
    initialize: function (app, options) {
        this.setOptions(options);
        this.app = app;
        this.wi = this.app.wi;
        this.srv = this.app.srv;
        this.util = this.app.util;
        this.path = "../x_component_CloudDocument/$User/";
    },
    addOrg : function (){
        o2.loadHtml(this.path + this.options.style + "/newOrg.html", function(loaded){
            var html = loaded[0].data;
            var footerNode = new Element("div");
            var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
            var createBtn = new Element("button",{text:"创建",class:"ant-btn ant-btn-primary"}).inject(footerNode);

            var bodyNode = new Element("div",{html:html});

            bodyNode.getElements(".teamIcon").addEvent("click",function(ev){
                if(bodyNode.getElement(".teamIconCheck")){
                    bodyNode.getElement(".teamIconCheck").destroy();
                }
                new Element("div",{"class":"teamIconCheck","html":'<i class="iconfont icon_check check"></i>'}).inject(ev.target);
            });

            var modal = this.wi.modal("创建企业",bodyNode,footerNode);
            cancelBtn.addEvent("click",function(){
                modal.destroy();
            });
            createBtn.addEvent("click",function(){

                this.srv.do("cloudDocumentManager","addCompany", {
                    "name": bodyNode.getElement("[data-o2-element=orgName]").get("value"),
                    "desc": bodyNode.getElement("[data-o2-element=orgDesc]").get("value")
                },function(json) {
                    this.wi.message("success","创建成功");
                    modal.destroy();
                }.bind(this));
            }.bind(this));
        }.bind(this));
    },
    userDetail: function () {
        this.srv.execute("getUserCapacity", {}, function (json) {
            layout.user.capacity = this.util.getFileSize(json.total);
            this.util.loadHtml(this.path + this.options.style + "/user_detail.html", layout.user, function (node) {
                this.wi.modal(null, node, null);
            }.bind(this))
        }.bind(this));
    },
    adminPanel: function () {
        layout.openApplication(null, "CloudDocumentManager", {});
    },
    logout: function () {
        if (layout.desktop.top) {
            layout.desktop.top.logout();
        } else if (layout.authentication) {
            layout.authentication.logout();
        } else {
            o2.Actions.get("x_organization_assemble_authentication").logout(function () {
                var host = window.location.hostname;
                hostList = host.split(".");
                hostList.shift();
                Cookie.dispose("x-token", {
                    "domain": "." + hostList.join("."),
                    "path": "/"
                });
                window.location.reload();
            }.bind(this));
        }
    }
});