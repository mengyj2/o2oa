o2.requireApp("CloudDocument", "Common", null, false);
o2.requireApp("CloudDocument", "Ant", null, false);
o2.requireApp("CloudDocument", "User", null, false);
o2.requireApp("CloudDocument", "Team", null, false);
o2.xApplication.CloudDocument.Main = new Class({
	Extends: o2.xApplication.Common.Main,
	Implements: [Options, Events],
	options: {
		"style": "default",
		"name": "CloudDocument",
		"mvcStyle": "style.css",
		"icon": "icon.png",
		"title": o2.xApplication.CloudDocument.LP.title
	},
	onQueryLoad: function(){
		this.lp = o2.xApplication.CloudDocument.LP;
		this.wi = new Ant.Wiget();
		this.srv = new o2.xApplication.CloudDocument.Service();
		this.util = new o2.xApplication.CloudDocument.Util();
		if(!layout.user.icon){
			layout.user.icon = this.lp.user.icon;
		}
		this.templatePath = this.path + this.options.style;
	},
	loadApplication: function(callback){
		this.content.loadHtml(this.path + this.options.style + "/view.html", { "module": this,"bind": {"lp": this.lp,"user":layout.user}}, function(){
			this.loadTeamList();
			this.loadDocument();
			this.setMenuAction();
		}.bind(this));
	},
	setMenuAction : function(){
		this.menuNode.getChildren().addEvent("click",function(ev){

			this.teamId = null;
			if(ev.target.getParent("li")){
				this.curMenuNode = ev.target.getParent("li");
			}else{
				this.curMenuNode = ev.target;
			}
			this.menuType = this.curMenuNode.get("menuType");
			this.loadContent();
			this.setCurMenu(this.curMenuNode);
			//this.setMenuAction();
		}.bind(this));
	},
	loadContent : function(){
		switch(this.menuType) {
			case "team":
				this.loadTeamDocument();
				this.actionNode.show();
				this.addOpNode.show();
				this.uploadOpNode.show();
				this.clearAllOpNode.hide();
				break;
			case "folder":
				this.loadDocument();
				this.actionNode.show();
				this.addOpNode.show();
				this.uploadOpNode.show();
				this.clearAllOpNode.hide();
				break;
			case "latest":
				this.loadDocumentLatest();
				this.actionNode.hide();
				break;
			case "share":
				this.loadShareToMe();
				this.actionNode.hide();
				break;
			case "fav":
				this.loadDocumentFav();
				this.actionNode.hide();
				break;
			case "recycle":
				this.loadRecycle();
				this.actionNode.show();
				this.addOpNode.hide();
				this.uploadOpNode.hide();
				this.clearAllOpNode.show();
				break;
			default:
				this.loadDocument();
				this.actionNode.show();
		}
	},
	setCurMenu : function(ev){
		if(ev){
			var target = ev.getParent(".ant-menu-item");
			if(!target) target = ev;
			target.addClass("ant-menu-item-selected");
			target.getSiblings().removeClass("ant-menu-item-selected");
			this.teamNode.getChildren().removeClass("menu-item--active");
		}else{
			this.teamNode.getChildren().removeClass("menu-item--active");
		}
	},
	setCurTeamMenu : function(ev){
		if(ev){
			var target = ev.target.getParent(".menu-item--special");
			if(!target) target = ev.target;
			target.addClass("menu-item--active");
			target.getSiblings().removeClass("menu-item--active");
			this.menuNode.getChildren().removeClass("ant-menu-item-selected");
		}else{
			this.menuNode.getChildren().removeClass("ant-menu-item-selected");
		}
	},
	loadTeamList : function(){
		this.teamNode.empty();
		this.srv.execute("getTeamList", {},function(json) {
			this.teamLit = json;
			json.each(function(d){
				var teamNode = new Element("div",{"class":"menu-item--special"}).inject(this.teamNode);
				var teamContainerNode = new Element("div",{"class":"team-name group-list-item ant-dropdown-trigger"}).inject(teamNode);
				var teamIconNode = new Element("span",{"class":"team-icon"}).inject(teamContainerNode);
				teamIconNode.set("html",'<div class="team-icon-wrap"><img src='+ this.path + this.options.style + "/img/team/" + d.icon +'.png></div>');
				var teamTextNode = new Element("span",{"class":"team-text"}).inject(teamContainerNode);
				teamTextNode.set("text",d.name);
				teamNode.addEvent("click",function(ev){
					this.setCurTeamMenu(ev);
					this.folderId = d.id;
					this.teamId = d.id;
					this.folderName = d.name;

					this.menuType = "team";
					this.loadContent();

				}.bind(this));

				var teamMoreNode = new Element("span",{"class":"team-menu-more ant-dropdown-trigger"}).inject(teamContainerNode);
				new Element("i",{"class":"iconfont icon_more2"}).inject(teamMoreNode);

				teamMoreNode.addEvent("click",function(ev){
					ev.stopPropagation();
					this.showTeamMenu(ev,d,teamNode);

				}.bind(this));
			}.bind(this));
		}.bind(this));
	},
	showTeamMenu : function(ev,data,teamNode){
		var bodyNode = new Element("div");

		bodyNode.loadHtml(this.path + this.options.style + "/team_more.html", { "module": new o2.xApplication.CloudDocument.Team(this,data,teamNode),"bind": {"lp": this.lp,"user":this.user}}, function(){
			this.newDropNode = this.wi.dropdown(ev,bodyNode);
			var teamSetTopNode = this.newDropNode.getElement(".teamSetTopNode");
			var teamSetUnTopNode = this.newDropNode.getElement(".teamSetUnTopNode")
			if(data.top){
				teamSetTopNode.hide();
				teamSetUnTopNode.show();
			}else{
				teamSetTopNode.show();
				teamSetUnTopNode.hide();
			}

		}.bind(this));
	},
	addTeam : function(){
		o2.loadHtml(this.path + this.options.style + "/newTeam.html", function(loaded){
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

			var modal = this.wi.modal("新建团队",bodyNode,footerNode);
			cancelBtn.addEvent("click",function(){
				modal.destroy();
			});
			createBtn.addEvent("click",function(){

				this.srv.execute("createTeam", {
					"icon" : bodyNode.getElement(".teamIconCheck").getParent().get("icon"),
					"name": bodyNode.getElement("[data-o2-element=teamName]").get("value"),
					"desc": bodyNode.getElement("[data-o2-element=teamDesc]").get("value")
				},function(json) {
					this.wi.message("success","创建成功");
					modal.destroy();
					this.loadTeamList();
				}.bind(this));
			}.bind(this));
		}.bind(this));

	},
//==========
	showUserPanel : function(ev){
		if(this.userPopNode) {
			this.userPopNode.show();
			return;
		}
		this.userPopNode = new Element("div.userPanel").inject(document.body);
		document.body.addEvent("mousedown",function(e){
			if(!e.target.getParent(".userPanel")){
				document.body.getElements(".userPanel").hide();
			}
		}.bind(this));
		layout.user.userName = layout.user.distinguishedName.split("@")[0];
		this.userPopNode.loadHtml(this.templatePath + "/user_pop.html", { "module": new o2.xApplication.CloudDocument.User(this),"bind": {"lp": this.lp,"user":layout.user}}, function(){
			// if(layout.user.roleList.contains("Manager@ManagerSystemRole@R")){
			// 	this.userPopNode.getElement(".adminPanel").show();
			// }
		}.bind(this));
	},
	loadDocumentLatest : function(ev){
		o2.xDesktop.requireApp("CloudDocument", "LatestExplorer", function () {
			// this.clearContent();
			this.explorer = new o2.xApplication.CloudDocument.LatestExplorer(this,this.contentNode,{"explorer":"LatestExplorer"});
		}.bind(this));
	},
	loadDocumentFav : function(ev){
		o2.xDesktop.requireApp("CloudDocument", "FavExplorer", function () {
			// this.clearContent();
			this.explorer = new o2.xApplication.CloudDocument.FavExplorer(this,this.contentNode,{"explorer":"FavExplorer"});

		}.bind(this));
	},
	loadShareToMe : function(ev){
		o2.xDesktop.requireApp("CloudDocument", "ShareToMeExplorer", function () {
			// this.clearContent();
			this.explorer = new o2.xApplication.CloudDocument.ShareToMeExplorer(this,this.contentNode,{"explorer":"ShareToMeExplorer"});

		}.bind(this));
	},
	loadMyShare : function(ev){
		o2.xDesktop.requireApp("CloudDocument", "MyShareExplorer", function () {
			// this.clearContent();
			this.explorer = new o2.xApplication.CloudDocument.MyShareExplorer(this,this.contentNode,{"explorer":"MyShareExplorer"});

		}.bind(this));
	},
	loadDocument : function(){
		this.menuType = "folder";
		o2.xDesktop.requireApp("CloudDocument", "Explorer", function () {
			// this.clearContent();
			var options = {
				"explorer":"Explorer"
			}
			this.explorer = new o2.xApplication.CloudDocument.Explorer(this,this.contentNode,options);
		}.bind(this));
	},
	loadTeamDocument : function(){
		this.breadNode.empty();
		this.createBread(this.folderName,this.folderId,"root");
		this.loadFileList();
	},
	loadRecycle : function(ev){
		o2.xDesktop.requireApp("CloudDocument", "RecycleExplorer", function () {
			// this.clearContent();
			this.explorer = new o2.xApplication.CloudDocument.RecycleExplorer(this,this.contentNode,{"explorer":"RecycleExplorer"});
		}.bind(this));
	},
	loadTeamRecycle : function(team){
		this.createSingleBread(team.name + "团队的回收站");
		this.srv.execute("queryDocumentByPage", {
			"page" : this.page,
			"pageSize" : this.pageSize,
			"isRemove" : true,
			"folderId" : team.id
		},function(json) {
			json.dataList.each(function(d){
				d.name = d.fileName;
			}.bind(this));
			this.toolsBtn = ["recycle","shiftRemove"];
			this.moreBtn = ["recycle","shiftRemove"];
			this.moreFolderBtn = [];
			this.parseDataList(json.dataList);
		}.bind(this));
	},
	search : function(ev){
		if(ev.keyCode===8){
			if(this.searchInputNode.get("value")===""){
				this.cancelSearch();
			}
		}
		if(ev.keyCode===13){
			if(this.searchInputNode.get("value")==="") return;
			//this.createSearchBread(this.searchInputNode.get("value"));
			this.searchCloseNode.show();
			o2.xDesktop.requireApp("CloudDocument", "SearchExplorer", function () {
				var options = {
					"searchKey" : this.searchInputNode.get("value"),
					"explorer":"SearchExplorer"
				}
				this.explorer = new o2.xApplication.CloudDocument.SearchExplorer(this,this.contentNode,options);
			}.bind(this));
		}
	},
	cancelSearch : function(){
		this.searchCloseNode.hide();
		this.searchInputNode.set("value","");
		this.loadContent();
	},
	openFolder : function(callback){

		o2.loadHtml(this.templatePath + "/folderList.html", function(loaded){
			var html = loaded[0].data;
			var bodyNode = new Element("div",{html:html});

			var treeNode = bodyNode.getElement(".tree-wrapper");

			this.createFolder(treeNode,"0");

			var footerNode = new Element("div");
			var cancelBtn = new Element("button",{text:"取消",class:"ant-btn ant-btn-ghost"}).inject(footerNode);
			var okBtn = new Element("button",{text:"确定",class:"ant-btn ant-btn-primary"}).inject(footerNode);

			this.folderModal = this.wi.modal("选择文件夹",bodyNode,footerNode,{"height":"400px","width":"500px"});
			cancelBtn.addEvent("click",function(){
				this.folderModal.destroy();
			}.bind(this));
			okBtn.addEvent("click",function(){
				if(this.folderModal.getElement(".ant-tree-node-selected")){
					var data = this.folderModal.getElement(".ant-tree-node-selected").retrieve("data");
					if(callback) callback(data);
					this.folderModal.destroy();
				}
			}.bind(this));
		}.bind(this));
	},
	createFolder:function(targetNode,folderId){

		var folderList = [];
		if(folderId === "0"){
			folderList.push({
				"id" : "-1",
				"name" : "我的文档"
			})
			// this.srv.execute("getTeamList", {
			// },function(json) {
			// 	json.each(function(d){
			// 		folderList.push(d);
			// 	})
			// }.bind(this));

		}else{
			this.srv.execute("getFolderList", {
				"folderId" : folderId
			},function(json) {
				folderList = json;
			}.bind(this));
		}

		var treeListNode = new Element("ul.ant-tree").inject(targetNode);
		folderList.each(function(d){
			var treeNode = new Element("li",{"class":"close"}).inject(treeListNode);
			var spanNode = new Element("span",{"class":"ant-tree-switcher"}).inject(treeNode);
			spanNode.set("html",'<i class="iconfont icon_right" style="font-size: 12px"></i>');
			var contentNode = new Element("span",{"class":"ant-tree-node-content-wrapper"}).inject(treeNode);
			var folderIconNode = new Element("span",{"class":"ant-tree-iconEle ant-tree-icon__customize"}).inject(contentNode);
			folderIconNode.set("html",'<i class="iconfont icon_folder"></i>');
			var titleNode = new Element("span",{"class":"ant-tree-title"}).inject(contentNode);
			titleNode.set("text",d.name);

			contentNode.addEvent("click",function(){
				if(this.folderModal.getElement(".ant-tree-node-selected")){
					this.folderModal.getElement(".ant-tree-node-selected").removeClass("ant-tree-node-selected");

				}
				contentNode.addClass("ant-tree-node-selected");
				contentNode.store("data",d);
			}.bind(this));

			spanNode.addEvent("click",function(){
				var status = treeNode.get("class");
				if(status==="close"){
					treeNode.set("class","open");
					spanNode.set("html",'<i class="iconfont icon_down2" style="font-size: 12px"></i>');
					folderIconNode.set("html",'<i class="iconfont icon_folder_open"></i>');
					this.createFolder(treeNode,d.id);
				}else{
					treeNode.set("class","close");
					spanNode.set("html",'<i class="iconfont icon_right" style="font-size: 12px"></i>');
					folderIconNode.set("html",'<i class="iconfont icon_folder"></i>');
					treeNode.getElement("ul").destroy();
				}
			}.bind(this));
		}.bind(this));
	},
});


