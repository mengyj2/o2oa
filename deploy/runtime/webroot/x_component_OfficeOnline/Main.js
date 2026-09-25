MWF.xAction.RestActions.Action["x_onlyofficefile_assemble_control"] = new Class({
	Extends: MWF.xAction.RestActions.Action
});
MWF.xApplication.OfficeOnline.options.multitask = false;
MWF.xDesktop.requireApp("Template", "MPopupForm", null, false);
MWF.xDesktop.requireApp("Template", "MForm", null, false);
MWF.xApplication.OfficeOnline.Main = new Class({
	Extends: MWF.xApplication.Common.Main,
	Implements: [Options, Events],
	options: {
		"style": "default",
		"name": "OfficeOnline",
		"mvcStyle": "style.css",
		"icon": "icon.png",
		"title": MWF.xApplication.OfficeOnline.LP.title
	},
	onQueryLoad: function(){
		this.lp = MWF.xApplication.OfficeOnline.LP;

		this.util = new MWF.xApplication.OfficeOnline.Util();
		//o2.loadCss("https://at.alicdn.com/t/font_3332487_duh1y70onzl.css");
	},
	loadApplication: function(callback){

		var url = this.path + this.options.style+"/view/view.html";
		this.content.loadHtml(url, {"bind": {"lp": this.lp}, "module": this}, function(){
			this.setLayout();

			this.loadList("all");
			if (callback) callback();
		}.bind(this));
	},

	setLayout: function(){
		var items = this.content.getElements(".menuItem");
		items.addEvents({
			"mouseover": function(){this.addClass("menuItem_over")},
			"mouseout": function(){this.removeClass("menuItem_over")},
			"click": function(){}
		});
	},
	loadList: function(type){

		if (this.currentMenu) this.setMenuItemStyleDefault(this.currentMenu);
		this.setMenuItemStyleCurrent(this[type+"MenuNode"]);
		this.currentMenu = this[type+"MenuNode"];
		this._loadListContent(type);
	},
	_loadListContent: function(type){

		this.mainNode.empty();

		list = new MWF.xApplication.OfficeOnline[type.capitalize() +"List"](this.mainNode,this, {
			"onLoadData": function (){
				this.hideSkeleton();
			},
			"type" : type,
			"key" : this.options.key
		});
		this.currentList = list;
	},
	setMenuItemStyleDefault: function(node){
		node.removeClass("mainColor_bg_opacity");
		node.getFirst().removeClass("mainColor_color");
		node.getLast().removeClass("mainColor_color");
	},
	setMenuItemStyleCurrent: function(node){
		node.addClass("mainColor_bg_opacity");
		node.getFirst().addClass("mainColor_color");
		node.getLast().addClass("mainColor_color");
	},
	recordStatus: function(){
		return {"navi": this.currentList.options.type};
	}
});
MWF.xApplication.OfficeOnline.List = new Class({
	Implements: [Options, Events],
	options: {
		"type": "all",
		"defaultViewType" : "list",
		"folderId" : "-1"
	},
	initialize: function (node,app, options) {
		this.setOptions(options);
		this.app = app;
		this.container = node;
		this.lp = this.app.lp;
		this.util = new MWF.xApplication.OfficeOnline.Util();
		this.action = app.action;
		this.type = this.options.type;
		var url = this.app.path + this.app.options.style+"/view/content.html";
		this.container.loadHtml(url, {"bind": {"lp": this.lp,"data":{"type":this.type}}, "module": this}, function(){
			this.content = this.listContentNode;

			this.init();
			this.load();

		}.bind(this));

	},
	inputFilter: function(e){
		if (e.keyCode==13) this.doFilter();
	},
	doFilter: function(){
		var key = this.searchKeyNode.get("value");
		this.searchKeyNode.set("value","");
		this.app.options.key = key;
		this.app.loadList("all");

	},
	showSkeleton: function(){

		if (this.skeletonNode) this.skeletonNode.inject(this.listContentNode);
	},
	hideSkeleton: function(){

		if (this.skeletonNode) this.skeletonNode.dispose();
	},
	loadListTitle : function (){
		this.listTitleNode.empty();
		this.listTitleNode.loadHtml(this.titleTempleteUrl, {"bind": {"lp": this.lp}, "module": this}, function(){
		}.bind(this));
	},

	selectAllFile : function (e){

		if (e.currentTarget.get("disabled").toString()!="true"){
			var itemNode = e.currentTarget.getParent(".listItem");
			var iconNode = e.currentTarget.getElement(".selectFlagIcon");

			if (itemNode){
				if (itemNode.hasClass("mainColor_bg_opacity")){
					itemNode.removeClass("mainColor_bg_opacity");
					iconNode.removeClass("o2icon-xuanzhong");
					iconNode.removeClass("selectFlagIcon_select");
					iconNode.removeClass("mainColor_color");


					this.listContentNode.getElements(this.toolbar.options.viewType === "list"?"tr":".listItem2").each(function (tr){
						tr.removeClass("mainColor_bg_opacity");
						var ss = tr.getElement(".selectFlagIcon");
						tr.getElement(".selectFlag").hide();
						ss.removeClass("o2icon-xuanzhong");
						ss.removeClass("selectFlagIcon_select");
						ss.removeClass("mainColor_color");

					})

					this.selectedList = [];

				}else{
					itemNode.addClass("mainColor_bg_opacity");
					iconNode.addClass("o2icon-xuanzhong");
					iconNode.addClass("selectFlagIcon_select");
					iconNode.addClass("mainColor_color");
					this.listContentNode.getElements(this.toolbar.options.viewType === "list"?"tr":".listItem2").each(function (tr){
						tr.getElement(".selectFlag").show();
						tr.addClass("mainColor_bg_opacity");
						var ss = tr.getElement(".selectFlagIcon");

						ss.addClass("o2icon-xuanzhong");
						ss.addClass("selectFlagIcon_select");
						ss.addClass("mainColor_color");

					})

					this.selectedList = this.dataList;
				}
			}
		}

		this._setToolBar();
	},
	loadItems: function(data){

		this.dataList = data;

		this.content.loadHtml(this.listTempleteUrl, {"bind": {"lp": this.lp, "type": this.options.type, "data": data}, "module": this}, function(){
			this.node = this.content.getFirst();
		}.bind(this));
	},
	init: function(){

		this.folderId = this.options.folderId;

		if(this.type === "all"){
			if(this.options.key){
				var keyContainer = new Element("div.ft_filterItem").inject(this.pathNode);
				new Element("div",{"class":"ft_filterItemTitle mainColor_color","text":"关键字："}).inject(keyContainer);
				new Element("div",{"class":"ft_filterItemName","text":this.options.key}).inject(keyContainer);
				var iconNode = new Element("icon",{"class":"o2icon-clear ft_filterItemDel"}).inject(keyContainer);

				iconNode.addEvent("click",function (ev){
					ev.target.getParent().hide();
					this.app.options.key = "";
					this.app.loadList("all");
				}.bind(this))
			}else {

				var rootPathNode = new Element("span",{"text":this.lp.allFile}).inject(this.pathNode);
				rootPathNode.addEvent("click",function(ev){
					this.app.currentList.folderId = this.options.folderId;
					this.app.currentList.refresh();
					ev.target.getAllNext().destroy();
				}.bind(this));
			}
		}else {
			this.pathNode.hide();
		}
	},
	_initTempate: function (){
		this.titleTempleteUrl = this.app.path+this.app.options.style+"/view/"+this.type+"/"+this.options.defaultViewType+"_title.html";
		this.listTempleteUrl = this.app.path+this.app.options.style+"/view/"+this.type+"/" +this.options.defaultViewType + ".html";
	},
	load: function(){


		var _self = this;

		this._initToolBar();
		this._initTempate();
		this.loadListTitle();

		this.loadToolBar(this.toolbarItems.unSelect);
		this.selectedList = [];
		this.loadData().then(function(data){
			_self.hide();

			_self.loadItems(data);
		});
	},
	_initToolBar : function (){
		this.toolbarItems = {
			"unSelect":[
				["upload"],
				["createFolder"],
				["createOffice"]

			],
			"selected":[
				["rename", "recycle"],
				["download", "move"],
				["share","folderSet","star"]
			],
			"mulSelect":[
				["recycle"],
				["move"],
				["share","star"]
			]
		}
	},
	loadToolBar : function (availableTool){

		this.toolBarNode.empty();
		this.toolbar = new MWF.xApplication.OfficeOnline.Toolbar(this.toolBarNode, this, {
			viewType : this.options.defaultViewType,
			type : this.type,
			availableTool : availableTool
		});
		this.toolbar.load();
	},
	refresh: function(){
		this.hide();
		this.load();
	},
	hide: function(){
		if (this.node) this.node.destroy();
	},
	loadData: function(){
		var _self = this;

		var dataList = [];
		if(this.options.key){
			return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
				"fun" : "queryDocumentByPage",
				"data" : {
					"folderId" :_self.folderId,
					"isRemove" : false,
					"key" : this.options.key
				}
			},function(json) {

				dataList.append(json.data.dataList);
				_self.fireEvent("loadData");
				return _self._fixData(dataList);

			}.bind(this));
		}else {


			if(this.folderId === "-1"){

				return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
					"fun" : "getFolderList",
					"data" : {
						"folderId" : "-1",
						"isRemove" : false,
						"key" : this.options.key
					}
				},function(json) {

					// //添加 共享给我的文件夹
					// var shareFolderData = {
					// 	"name" : "共享给我的文件夹",
					// 	"type" : "folder",
					// 	"id" : "0"
					// }
					// dataList.push(shareFolderData);
					dataList.append(json.data);

					return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
						"fun" : "queryDocumentByPage",
						"data" : {
							"folderId" : "-1",
							"fileType" : this.options.fileType,
							"isRemove" : false
						}
					},function(json) {

						dataList.append(json.data.dataList);
						_self.fireEvent("loadData");
						return _self._fixData(dataList);

					}.bind(this));
				}.bind(this));

			}else if(this.folderId === "0"){
				return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
					"fun" : "getShareFolderList",
					"data" : {
						"folderId" : "-1",
						"isRemove" : false
					}
				},function(json) {

					dataList.append(json.data);

					_self.fireEvent("loadData");
					return _self._fixData(dataList);
				}.bind(this));
			}else {


				return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
					"fun" : "getFolderList",
					"data" : {
						"folderId" : _self.folderId,
						"isRemove" : false
					}
				},function(json) {
					dataList = json.data;
					return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
						"fun" : "queryDocumentByPage",
						"data" : {
							"folderId" :_self.folderId,
							"isRemove" : false
						}
					},function(json) {

						dataList.append(json.data.dataList);
						_self.fireEvent("loadData");
						return _self._fixData(dataList);

					}.bind(this));
				}.bind(this));

			}
		}

	},
	_fixData : function (dataList){
		dataList.each(function (data){

			if(!data.folderId){
				data.fileType = "folder";
				data.type = "folder";
			}else{
				data.name = data.fileName;
			}

			console.log("data.length:" + data.fileSize)
			data.length = this.util.getFileSize(data.fileSize);

			data.fileType = this.util.getFileExtension(data.fileType);

		}.bind(this));
		return dataList;
	},

	overTaskItem: function(e){
		e.currentTarget.addClass("listItem_over");

		var iconNode = e.currentTarget.getElement(".selectFlagIcon");
		if (iconNode.hasClass("selectFlagIcon_select")){

		}else{
			e.currentTarget.getElement(".selectFlag").show();
		}
	},
	outTaskItem: function(e){
		e.currentTarget.removeClass("listItem_over");
		var iconNode = e.currentTarget.getElement(".selectFlagIcon");

		if (iconNode.hasClass("selectFlagIcon_select")){

		}else{
			e.currentTarget.getElement(".selectFlag").hide();
		}
	},
	star : function(id,e) {
		alert(id)
	},
	open: function(id,e){
		var data ;
		for(var i = 0 ; i < this.dataList.length;i++){
			if(this.dataList[i].id === id){
				data = this.dataList[i];
				break ;
			}
		}
		if(data.type === "folder"){
			this.folderId = data.id;
			this.refresh();
			var folderPathNode = new Element("span",{"text":data.name,"style":"padding-left:10px;margin-left:10px; background: url('/x_component_File/$Main/default/icon/next.png') center left no-repeat;"}).inject(this.pathNode);
			folderPathNode.store("data",data);
			folderPathNode.addEvent("click",function(ev){

				var data = ev.target.retrieve("data");
				this.folderId = data.id;
				this.refresh();
				ev.target.getAllNext().destroy();
			}.bind(this));


		}else{
			// new MWF.xApplication.OfficeOnline.AttachmenPreview(data,this);
			var options = {
				"documentId": data.id,
				"mode":"edit",
				"jars" : "officeOnline",
				"appId":  "OnlyOfficeEditor" + data.id
			};
			layout.openApplication(null, "OnlyOfficeEditor", options);
		}

	},
	selectFile: function(id,e, dataList){

		var data ;
		for(var i = 0 ; i < this.dataList.length;i++){
			if(this.dataList[i].id === id){
				data = this.dataList[i];
				break ;
			}
		}

		if (e.currentTarget.get("disabled").toString()!="true"){
			var itemNode = e.currentTarget.getParent(".listItem");
			var iconNode = e.currentTarget.getElement(".selectFlagIcon");

			if (itemNode){
				if (itemNode.hasClass("mainColor_bg_opacity")){
					itemNode.removeClass("mainColor_bg_opacity");
					iconNode.removeClass("o2icon-xuanzhong");
					iconNode.removeClass("selectFlagIcon_select");
					iconNode.removeClass("mainColor_color");
					this.unselectedFile(data);
				}else{
					itemNode.addClass("mainColor_bg_opacity");
					iconNode.addClass("o2icon-xuanzhong");
					iconNode.addClass("selectFlagIcon_select");
					iconNode.addClass("mainColor_color");
					this.selectedFile(data);
				}
			}
		}

		this._setToolBar();

	},
	_setToolBar: function () {
		if (this.selectedList.length === 0) {
			this.loadToolBar(this.toolbarItems.unSelect);
		} else if (this.selectedList.length === 1) {
			this.loadToolBar(this.toolbarItems.selected);
		} else {
			this.loadToolBar(this.toolbarItems.mulSelect);
		}
	},
	selectedFile: function(data){
		if (!this.selectedList) this.selectedList = [];
		var idx = this.selectedList.findIndex(function(t){
			return t.id == data.id;
		});
		if (idx===-1) this.selectedList.push(data);
	},
	unselectedFile: function(data){
		// delete data._;
		if (!this.selectedList) this.selectedList = [];
		var idx = this.selectedList.findIndex(function(t){
			return t.id == data.id;
		});
		if (idx!==-1) this.selectedList.splice(idx, 1);
	}
});
MWF.xApplication.OfficeOnline.AllList = new Class({
	Extends: MWF.xApplication.OfficeOnline.List
});
MWF.xApplication.OfficeOnline.DocxList = new Class({
	Extends: MWF.xApplication.OfficeOnline.List,
	loadData: function(){
		var _self = this;
		return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "queryDocumentByPage",
			"data" : {
				"fileType" : "docx",
				"isRemove" : false
			}
		},function(json) {

			_self.fireEvent("loadData");
			return _self._fixData(json.data.dataList);

		}.bind(this));
	},
});
MWF.xApplication.OfficeOnline.XlsxList = new Class({
	Extends: MWF.xApplication.OfficeOnline.List,
	loadData: function(){
		var _self = this;
		return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "queryDocumentByPage",
			"data" : {
				"fileType" : "xlsx",
				"isRemove" : false
			}
		},function(json) {

			_self.fireEvent("loadData");
			return _self._fixData(json.data.dataList);

		}.bind(this));
	},
});
MWF.xApplication.OfficeOnline.PptxList = new Class({
	Extends: MWF.xApplication.OfficeOnline.List,
	loadData: function(){
		var _self = this;
		return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "queryDocumentByPage",
			"data" : {
				"fileType" : "pptx",
				"isRemove" : false
			}
		},function(json) {

			_self.fireEvent("loadData");
			return _self._fixData(json.data.dataList);

		}.bind(this));
	},
});
MWF.xApplication.OfficeOnline.LatestList = new Class({
	Extends: MWF.xApplication.OfficeOnline.List,
	loadData: function(){
		var _self = this;
		return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "queryLatestByPage",
			"data" : {
			}
		},function(json) {

			_self.fireEvent("loadData");
			return _self._fixData(json.data.dataList);

		}.bind(this));
	},
});
MWF.xApplication.OfficeOnline.StarList = new Class({
	Extends: MWF.xApplication.OfficeOnline.List,
	loadData: function(){
		var _self = this;
		return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "queryFavByPage",
			"data" : {
			}
		},function(json) {

			_self.fireEvent("loadData");
			return _self._fixData(json.data.dataList);

		}.bind(this));
	},
	_initToolBar : function (){

		this.toolbarItems = {
			"unSelect":[
			],
			"selected":[
				["download"],
				["share","unstar"]
			],
			"mulSelect":[
				["share","unstar"]
			]
		}
	},
});
MWF.xApplication.OfficeOnline.MyShareList = new Class({
	Extends: MWF.xApplication.OfficeOnline.List,
	loadData: function(){
		var _self = this;
		return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "queryMyShareByPage",
			"data" : {
			}
		},function(json) {

			_self.fireEvent("loadData");
			return _self._fixData(json.data.dataList);

		}.bind(this));
	},
	_initToolBar : function (){
		this.toolbarItems = {
			"unSelect":[

			],
			"selected":[
				["cancelShare"]
			],
			"mulSelect":[

			]
		}
	},
});
MWF.xApplication.OfficeOnline.ShareToMeList = new Class({
	Extends: MWF.xApplication.OfficeOnline.List,
	loadData: function(){
		var _self = this;
		return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "queryShareToMeByPage",
			"data" : {
			}
		},function(json) {

			_self.fireEvent("loadData");
			return _self._fixData(json.data.dataList);

		}.bind(this));
	},
	_initToolBar : function (){

		this.toolbarItems = {
			"unSelect":[

			],
			"selected":[
				["download"]
			],
			"mulSelect":[
			]
		}
	},
});
MWF.xApplication.OfficeOnline.RecycleList = new Class({
	Extends: MWF.xApplication.OfficeOnline.List,
	loadData: function(){
		var _self = this;
		return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "getFolderList",
			"data" : {

				"isRemove" : true
			}
		},function(json) {
			dataList = json.data;
			return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
				"fun" : "queryDocumentByPage",
				"data" : {
					"isRemove" : true
				}
			},function(json) {

				dataList.append(json.data.dataList);
				_self.fireEvent("loadData");
				return _self._fixData(dataList);

			}.bind(this));
		}.bind(this));
	},
	_initToolBar : function (){

		this.toolbarItems = {
			"unSelect":[
				["clear"]
			],
			"selected":[
				["restore","delete"]
			],
			"mulSelect":[
				["restore","delete"]
			]
		}
	},
});
MWF.xApplication.OfficeOnline.FolderList = new Class({
	Implements: [Options, Events],
	options: {
		"folderId" : "-1"
	},
	initialize: function (node,app,explorer,options) {
		this.setOptions(options);

		this.app = app;
		this.lp = app.lp;
		this.content = node;

		this.explorer = explorer;
		this.type = this.options.type;
		this.action = app.action;
	},
	init: function(){

		this.folderId = this.options.folderId;

		this.pathNode = new Element("div").inject(this.content);
		var rootPathNode = new Element("span",{"text":this.lp.allFile}).inject(this.pathNode);
		rootPathNode.addEvent("click",function(ev){
			this.explorer.folderList.folderId = this.options.folderId;
			this.explorer.folderList.refresh();
			ev.target.getAllNext().destroy();
		}.bind(this));
	},
	load: function(){

		var _self = this;
		this.loadData().then(function(data){
			_self.dataList = data;
			_self.hide();
			_self.loadItems(data);
		});
	},
	refresh: function(){
		this.hide();
		this.load();
	},
	hide: function(){
		if (this.node) this.node.destroy();
	},
	loadData: function(){

		return o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "getFolderList",
			"data" : {
				"folderId" : this.folderId,
				"isRemove" : false
			}
		},function(json) {
			return json.data;
		}.bind(this));
	},
	loadItems: function(data){

		var url = this.app.path+this.app.options.style+"/view/folder/list.html";
		this.content.loadHtml(url, {"bind": {"lp": this.lp, "type": this.options.type, "data": data}, "module": this}, function(){
			this.node = this.content.getElement(".tableBody");

		}.bind(this));
	},
	overTaskItem: function(e){
		e.currentTarget.addClass("listItem_over");

	},
	outTaskItem: function(e){
		e.currentTarget.removeClass("listItem_over");

	},
	open: function(id,e){
		var data ;
		for(var i = 0 ; i < this.dataList.length;i++){
			if(this.dataList[i].id === id){
				data = this.dataList[i];
				break ;
			}
		}
		this.folderId = id;
		this.refresh();

		var folderPathNode = new Element("span",{"text":data.name,"style":"padding-left:10px;margin-left:10px; background: url('/x_component_File/$Main/default/icon/next.png') center left no-repeat;"}).inject(this.pathNode);
		folderPathNode.store("data",data);
		folderPathNode.addEvent("click",function(ev){

			var data = ev.target.retrieve("data");
			this.folderId = data.id;
			this.refresh();
			ev.target.getAllNext().destroy();
		}.bind(this));
	},
});
MWF.xApplication.OfficeOnline.Toolbar = new Class({
	Extends: MWF.widget.Common,
	Implements: [Options, Events],
	options: {
		"style": "default",
		"viewType" : "list",
		"type" : "all"
	},
	initialize : function( container, explorer, options ) {

		this.container = container;
		this.explorer = explorer;
		this.app = explorer.app;
		this.lp = explorer.app.lp;

		this.action = explorer.action;

		this.setOptions(options);

		this._initTools();
		this.type = this.options.type;

		this.availableTool = this.options.availableTool;


	},
	_initTools : function (){
		this.tools = {
			upload : {
				action : "upload",
				text : "上传",
				icon : "icon-upload"
			},
			createFolder : {
				action : "createFolder",
				text : "新建文件夹",
				icon : "icon-newfolder"
			},
			createOffice : {
				action : "createOffice",
				text : "新建在线文档",
				icon : "icon-newfolder"
			},
			folderSet : {
				action : "setZoneAcl",
				text : "共享",
				icon : "icon-rename",
				condition : "function(d){return d.type ==='folder'}"
			},
			rename : {
				action : "rename",
				text : "重命名",
				icon : "icon-rename"
			},
			download : {
				action : "download",
				text : "下载",
				icon : "icon-shareDownload",
				condition : "function(d){return d.type !=='folder'}"

			},
			star : {
				action : "star",
				text : "收藏",
				icon : "icon-star"
			},
			unstar : {
				action : "unstar",
				text : "取消收藏",
				icon : "icon-star"
			},
			shareDownload : {
				action : "shareDownload",
				text : "下载",
				icon : "icon-shareDownload"
			},
			saveTo : {
				action : "saveTo",
				text : "保存到...",
				icon : "icon-shareSave"
			},
			saveZoneTo : {
				action : "saveZoneTo",
				text : "保存到网盘",
				icon : "icon-shareSave"
			},
			shareShield : {
				action : "shareShield",
				text : "屏蔽",
				icon : "icon-shield"
			},
			move : {
				action : "move",
				text : "移动",
				icon : "icon-move"
			},
			recycle : {
				action : "recycle",
				text : "删除",
				icon : "icon-delete"
			},
			delete : {
				action : "delete",
				text : "彻底删除",
				icon : "icon-delete"
			},
			share : {
				action : "setZoneAcl",
				text : "分享设置",
				icon : "icon-share1",
				condition : "function(d){return d.type !=='folder'}"

			},
			cancelShare : {
				action : "setZoneAcl",
				text : "分享设置",
				icon : "icon-shareCancel"
			},
			restore : {
				action : "restore",
				text : "恢复",
				icon : "icon-restore"
			},
			clear : {
				action : "clear",
				text : "清空回收站",
				icon : "icon-clear"
			},
			editZone : {
				action : "editZone",
				text : "编辑",
				icon : "icon-rename"
			},
			setZoneAcl : {
				action : "setZoneAcl",
				text : "设置权限",
				icon : "icon-rename"
			},
			editZone : {
				action : "editZone",
				text : "编辑",
				icon : "icon-rename"
			},
			deleteZone : {
				action : "deleteZone",
				text : "删除",
				icon : "icon-delete"
			},
			addCapacity : {
				action : "addCapacity",
				text : "添加",
				icon : "icon-upload"
			}
			,
			deleteCapacity : {
				action : "deleteCapacity",
				text : "删除",
				icon : "icon-delete"
			}
		}
	},
	getConditionResult: function (str) {
		var flag = true;

		if (str && str.substr(0, 8) == "function") { //"function".length
			eval("var fun = " + str);
			if(this.explorer.selectedList){
				var data = this.explorer.selectedList[0];
			}else {
				var data = {}
			}
			flag = fun.call(this, data);

		}
		return flag;
	},
	load : function(){

		this.node = new Element("div").inject( this.container );

		this.availableTool.each( function( group ){
			var toolgroupNode = new Element("div.toolgroupNode").inject( this.node );
			var length = group.length;
			group.each( function( t, i ){
				var className;
				if( length == 1 ){
					className = "toolItemNode_single";
				}else{
					if( i == 0 ){
						className = "toolItemNode_left";
					}else if( i + 1 == length ){
						className = "toolItemNode_right";
					}else{
						className = "toolItemNode_center";
					}
				}

				var tool = this.tools[t];

				var flag = true;
				if( tool.condition){

					flag = this.getConditionResult(tool.condition);

				}
				if(flag){
					var toolNode = new Element( "div", {
						class : className,
						style : "cursor:pointer;height:30px;line-height:30px;padding-left:12px;padding-right:12px;background: #4A90E2;font-size: 13px;color: #FFFFFF;font-weight: 400;",
						events : {
							click : function( ev ){ this[tool.action]( ev ) }.bind(this)
						}
					}).inject( toolgroupNode );

					var iconNode = new Element("icon",{"class":"o2Drive " + tool.icon,"style":"margin-right:6px"}).inject(toolNode);
					var textNode = new Element("span").inject(toolNode);
					textNode.set("text",tool.text);
				}

			}.bind(this))
		}.bind(this));

		this.loadRightNode()
	},
	getDocumentAcl : function(acl){
		//1.可查看、创建和修改文档
		//2.只读
		//3.拒绝访问
		//4.审阅
		//5.Form Filling
		//6.评论
		var aclAliasArr = [0,1,2,3,4,5,6];
		var aclNameArr = ["创建者","可查看、创建和修改文档","只读","审阅","表单填报","评论","拒绝访问"];
		var aclName ;
		for(var i = 0 ; i < aclAliasArr.length ; i ++){
			if(aclAliasArr[i]===acl){
				aclName = aclNameArr[i];
			}
		}
		return aclName;
	},
	setZoneAcl : function (){

		var _self = this;
		var zoneNode = new Element("div");

		var data = this.explorer.selectedList[0];


		o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : data.type !== "folder"?"getDocumentAcl":"getFolderAcl",
			"data" : {
				"documentId": data.id,
				"folderId" : data.id
			}
		},function(json) {
			console.log(json);

			json.data.each(function(d){
				d.aclName = this.getDocumentAcl(d.acl);
				d.id = data.id;
			}.bind(this));

			var zoneNode = new Element("div");

			this.zoneNode = zoneNode;
			var url = this.app.path+this.app.options.style+"/view/dlg/zone.html";
			zoneNode.loadHtml(url, {"bind": {"lp": this.lp,"data":json.data}, "module": this})

			this.zoneDlg = o2.DL.open({
				"title": data.name + "分享设置",
				"style": "user",
				"isResize": false,
				"content": zoneNode,
				"maskNode": this.app.content,
				"minTop": 5,
				"width": "800",
				"height": "600",
				"buttonList": [
					{
						"type": "ok",
						"text": "添加",
						"styles" : {
							"border": "0px",
							"background-color": "#4A90E2",
							"height": "30px",
							"float" : "left",
							"border-radius": "20px",
							"min-width": "80px",
							"margin": "10px 10px 10px 30px",
							"color": "#ffffff"
						},

						"action": function (d, e) {

							var opt = {
								"types": ["identity"],
								"count": 0,
								"title": "添加成员",
								"values":[],
								"onComplete": function (items) {

									var dataList = [];
									items.each(function(item){
										dataList.push({
											person : item.data.woPerson.unique,
											personName : item.data.woPerson.name,
											acl : 2
										})
									})


									o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
										"fun" : "addAcl",
										"data" : {
											documentId : data.id,
											dataList : dataList
										}
									},function(json) {
										this._reloadZoneAcl(data.id);
									}.bind(this))

								}.bind(this)
							};
							o2.xDesktop.requireApp("Selector", "package", function(){
								new o2.O2Selector(this.app.content, opt);
							}.bind(this), false);

						}.bind(this)
					},
					{
						"type": "cancel",
						"text": "关闭",
						"action": function () {
							this.zoneDlg.close();
							zoneNode.destroy();
							//_self.content.unmask();
						}.bind(this)
					}
				],
				"onPostLoad": function () {

				}
			});
		}.bind(this))


	},
	_reloadZoneAcl : function (id){
		var data = this.explorer.selectedList[0];
		this.zoneNode.empty();
		o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : data.type !== "folder"?"getDocumentAcl":"getFolderAcl",
			"data" : {
				"documentId": data.id,
				"folderId" : data.id
			}
		},function(json) {

			json.data.each(function(d){
				d.aclName = this.getDocumentAcl(d.acl);
				d.id = id;
			}.bind(this));

			var url = this.app.path+this.app.options.style+"/view/dlg/zone.html";
			this.zoneNode.loadHtml(url, {"bind": {"lp": this.lp,"data":json.data}, "module": this})

		}.bind(this))

	},
	setRoleAcl : function (person,ev,dataList){

		var data ;
		for(var i = 0 ; i < dataList.length;i++){
			if(dataList[i].person === person){
				data = dataList[i];
				break ;
			}
		}

		if(data.aclName === "创建者") return ;

		if (this.filterDlg) return;
		var node = ev.target;

		this.currentRoleNode  = node;

		var position = node.getPosition();
		var y = position.y-60;
		var x = position.x - 40;
		var fx = position.x;

		var filterContent = new Element("div");
		var url = this.app.path+this.app.options.style+"/view/dlg/roleAclMore.html";
		filterContent.loadHtml(url, {"bind": {"lp": this.lp, "type": this.options.type,"data":data}, "module": this})

		var _self = this;
		var closeFilterDlg = function(){
			_self.filterDlg.close();
		}
		this.filterDlg = o2.DL.open({
			"mask": false,
			"title": "",
			"style": "user",
			"isMove": false,
			"isResize": false,
			"isTitle": false,
			"content": filterContent,
			"top": y,
			"left": x,
			"fromTop": y,
			"fromLeft": fx,
			"width": 200,
			"height": 180,
			"duration": 100,
			// "onQueryClose": function(){
			// 	document.body.removeEvent("mousedown", closeFilterDlg);
			// },
			"onPostClose": function(){
				document.body.removeEvent("mousedown", closeFilterDlg);
				_self.filterDlg = null;
			}

		});
		this.filterDlg.node.addEvent("mousedown", function(e){
			e.stopPropagation();
		});
		document.body.addEvent("mousedown", closeFilterDlg);


	},
	saveRoleAcl : function (type,ev,data){

		console.log(data)

		this.filterDlg.close();
		this.currentRoleNode.set("text",this.getDocumentAcl(parseInt(type)));


		o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "updateAcl",
			"data" : {
				documentId : data.id,
				aclPerson : data.person,
				acl : type
			}
		},function(json) {
			console.log(json);
		}.bind(this))

	},
	removeRoleAcl : function(ev,data){
		this.filterDlg.close();
		this.currentRoleNode.getParent("tr").hide();

		o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
			"fun" : "removeAcl",
			"data" : {
				documentId : data.id,
				aclPerson : data.person
			}
		},function(json) {
			console.log(json);
		}.bind(this))
	},
	editZone : function (){
		var _self = this;
		var zoneNode = new Element("div");

		var data = this.explorer.selectedList[0];

		var url = this.app.path+this.app.options.style+"/view/dlg/editZone.html";
		zoneNode.loadHtml(url, {"bind": {"lp": this.lp,"data":data}, "module": this})

		this.zoneDlg = o2.DL.open({
			"title": "修改共享区",
			"style": "user",
			"isResize": false,
			"content": zoneNode,
			"maskNode": this.app.content,
			"minTop": 5,
			"width": "500",
			"height": "400",
			"buttonList": [
				{
					"type": "ok",
					"text": "确定",
					"action": function (d, e) {

						var name = zoneNode.getElement("input").get("value");
						var description = zoneNode.getElement("textarea").get("value");

						this.action.ZoneAction.update(data.zoneId,{
							"name" : name,
							"description" : description
						}).then(function(json){
							_self.zoneDlg.close();
							zoneNode.destroy();
							_self.app.notice("修改成功");
							_self.explorer.refresh();
						});

					}.bind(this)
				},
				{
					"type": "cancel",
					"text": "取消",
					"action": function () {
						this.zoneDlg.close();
						zoneNode.destroy();
						//_self.content.unmask();
					}.bind(this)
				}
			],
			"onPostLoad": function () {

			}
		});
	},
	deleteZone : function (e){

	},
	move : function (){
		var _self = this;
		var zoneNode = new Element("div");

		this.folderList = new MWF.xApplication.OfficeOnline.FolderList(zoneNode,this.app,this, {
			folderId : "-1",
			type : this.explorer.type
		});
		this.folderList.init();
		this.folderList.load();

		this.zoneDlg = o2.DL.open({
			"title": "移动到",
			"style": "user",
			"isResize": false,
			"content": zoneNode,
			"maskNode": this.app.content,
			"minTop": 5,
			"width": "600",
			"height": "400",
			"buttonList": [
				{
					"type": "ok",
					"text": "确认",
					"action": function (d, e) {

						var dataList = this.explorer.selectedList;
						this.app.confirm("warn", e, "移动文件确认", "是否移动选中的"+dataList.length+"个文件？", 350, 120, function () {
							var count = 0;
							dataList.each( function(data){

								var folderId = _self.folderList.folderId==="-1"?"":_self.folderList.folderId;


								o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
									"fun" : data.fileType==="folder"?"moveFolder":"moveDocument",
									"data" : {
										"documentId": data.id,
										"folderId" : data.id,
										"newFolderId" :_self.folderList.folderId
									}
								},function(json) {
									count++;
									if( dataList.length == count ){
										_self.app.notice("成功移动"+count+"个文件。");
										_self.explorer.refresh();
										_self.zoneDlg.close();
										zoneNode.destroy();
									}
								}.bind(this))


							}.bind(this));
							this.close();
						}, function () {
							this.close();
						});

					}.bind(this)
				},
				{
					"type": "cancel",
					"text": "取消",
					"action": function () {
						this.zoneDlg.close();
						zoneNode.destroy();
						//_self.content.unmask();
					}.bind(this)
				}
			],
			"onPostLoad": function () {

			}
		});
	},
	saveTo : function (){
		var _self = this;
		var zoneNode = new Element("div");

		this.folderList = new MWF.xApplication.OfficeOnline.FolderList(zoneNode,this.app,this, {
			folderId : this.explorer.type === "zone"?this.explorer.app.zoneId:"-1",
			type : this.explorer.type
		});
		this.folderList.init();
		this.folderList.load();

		this.zoneDlg = o2.DL.open({
			"title": "保存到",
			"style": "user",
			"isResize": false,
			"content": zoneNode,
			"maskNode": this.app.content,
			"minTop": 5,
			"width": "600",
			"height": "400",
			"buttonList": [
				{
					"type": "ok",
					"text": "确认",
					"action": function (d, e) {

						var dataList = this.explorer.selectedList;

						var count = 0;
						dataList.each( function(data){

							var folderId = _self.folderList.folderId==="-1"?"(0)":_self.folderList.folderId;

							if(this.explorer.shareId === data.id){
								var fileId = data.id;
								var shareId = this.explorer.shareId;
							}else {
								var fileId = data.fileId;
								var shareId = data.id
							}
							debugger

							_self.action.ShareAction.saveToFolder(shareId,fileId,folderId,{
							} ,function(){
								count++;
								if( dataList.length == count ){
									_self.app.notice("保存成功"+count+"个文件。");
									_self.explorer.refresh();
									_self.zoneDlg.close();
									zoneNode.destroy();
								}
							});

						}.bind(this));

					}.bind(this)
				},
				{
					"type": "cancel",
					"text": "取消",
					"action": function () {
						this.zoneDlg.close();
						zoneNode.destroy();
						//_self.content.unmask();
					}.bind(this)
				}
			],
			"onPostLoad": function () {

			}
		});
	},
	saveZoneTo : function (){
		var _self = this;
		var zoneNode = new Element("div");

		this.folderList = new MWF.xApplication.OfficeOnline.FolderList(zoneNode,this.app,this, {
			folderId : "-1",
			type : "all"
		});
		this.folderList.init();
		this.folderList.load();

		this.zoneDlg = o2.DL.open({
			"title": "保存到",
			"style": "user",
			"isResize": false,
			"content": zoneNode,
			"maskNode": this.app.content,
			"minTop": 5,
			"width": "600",
			"height": "400",
			"buttonList": [
				{
					"type": "ok",
					"text": "确认",
					"action": function (d, e) {

						var folderId = _self.folderList.folderId==="-1"?"(0)":_self.folderList.folderId;

						var dataList = this.explorer.selectedList;
						var attIdList = [];
						var folderIdList = [];


						dataList.each(function (d){
							if(d.type === "folder"){
								folderIdList.push(d.id);
							}else {
								attIdList.push(d.id);
							}
						})

						_self.action.Folder3Action.saveToZone(folderId,{
							"attIdList" : attIdList,
							"folderIdList" : folderIdList
						} ,function(){
							_self.app.notice("保存成功");
							_self.explorer.refresh();
							_self.zoneDlg.close();
							zoneNode.destroy();
						});

					}.bind(this)
				},
				{
					"type": "cancel",
					"text": "取消",
					"action": function () {
						this.zoneDlg.close();
						zoneNode.destroy();
						//_self.content.unmask();
					}.bind(this)
				}
			],
			"onPostLoad": function () {

			}
		});
	},
	createFolder : function(){
		var form = new MWF.xApplication.OfficeOnline.FolderForm(this.explorer, {
		}, {}, {
			app: this.app
		});
		form.create()
	},
	createOffice : function(){
		var form = new MWF.xApplication.OfficeOnline.OfficeForm(this.explorer, {
		}, {}, {
			app: this.app
		});
		form.create()
	},
	cancelShare : function (e){
		var _self = this;
		var dataList = this.explorer.selectedList;
		this.app.confirm("warn", e, "取消分享确认", "是否取消选中的"+dataList.length+"个文件的分享？", 350, 120, function () {
			var count = 0;
			dataList.each( function(data){
				_self.action.ShareAction.delete( data.id , function(){
					count++;
					if( dataList.length == count ){
						_self.app.notice("取消分享成功");
						_self.explorer.refresh();
					}
				});
			}.bind(this));
			this.close();
		}, function () {
			this.close();
		});
	},
	rename : function(){

		var _self = this;
		if (this.explorer.selectedList && this.explorer.selectedList.length){
			var data = this.explorer.selectedList[0];
			var form = new MWF.xApplication.OfficeOnline.ReNameForm(this.explorer, data, {
			}, {
				app: this.app
			});
			form.edit()
		}else {
			this.app.notice("请先选择文件","error");
			return;
		}

	},
	recycle : function( e ){
		var _self = this;
		if (this.explorer.selectedList && this.explorer.selectedList.length){
			var dataList = this.explorer.selectedList;
			this.app.confirm("warn", e, "删除文件确认", "是否删除选中的"+dataList.length+"个文件？删除的文件会放到回收站。", 350, 120, function () {
				var count = 0;
				dataList.each( function(data){

					o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv", {
						"fun": data.type==="folder"?"removeFolder":"removeDocument",
						"data": {
							"documentId": data.id,
							"folderId" : data.id,
							"soft" :true
						}
					}, function (json) {
						count++;
						if( dataList.length == count ){
							_self.app.notice("成功删除"+count+"个文件，您可以从回收站找到文件。");
							_self.explorer.refresh();
						}

					}.bind(this));

				}.bind(this));
				this.close();
			}, function () {
				this.close();
			});
		}else {
			this.app.notice("请先选择文件","error");
			return;
		}
	},
	unstar: function (e){
		var dataList = this.explorer.selectedList;
		var count = 0;
		dataList.each( function(data){

			o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv", {
				"fun": "deleteFav",
				"data": {
					"documentId": data.id
				}
			}, function (json) {
				count++;
				if( dataList.length == count ){
					this.app.notice("成功收藏"+count+"个文件。");
					this.explorer.refresh();
				}
			}.bind(this));
		}.bind(this));

	},
	star : function (e){
		var dataList = this.explorer.selectedList;
		var count = 0;
		dataList.each( function(data){

			o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv", {
				"fun": "addFav",
				"data": {
					"documentId": data.id
				}
			}, function (json) {
				count++;
				if( dataList.length == count ){
					this.app.notice("成功收藏"+count+"个文件。");
					this.explorer.refresh();
				}
			}.bind(this));
		}.bind(this));

	},
	delete : function (e){
		var _self = this;
		var dataList = this.explorer.selectedList;
		this.app.confirm("warn", e, "删除文件确认", "是否删除选中的"+dataList.length+"个文件？删除的文件不能恢复。", 350, 120, function () {
			var count = 0;
			dataList.each( function(data){

				o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv", {
					"fun": data.type==="folder"?"removeFolder":"removeDocument",
					"data": {
						"documentId": data.id,
						"folderId" : data.id,
						"soft" :false
					}
				}, function (json) {
					count++;
					if( dataList.length == count ){
						_self.app.notice("成功删除"+count+"个文件。");
						_self.explorer.refresh();
					}

				}.bind(this));

			}.bind(this));
			this.close();
		}, function () {
			this.close();
		});
	},
	deleteCapacity : function (e){
		var _self = this;
		var dataList = this.explorer.selectedList;
		this.app.confirm("warn", e, "删除确认", "是否删除选中的"+dataList.length+"的配置", 350, 120, function () {
			var count = 0;
			dataList.each( function(data){
				_self.action.ConfigAction.deletePersonConfig( data.id , function(){
					count++;
					if( dataList.length == count ){
						_self.app.notice("成功删除");
						_self.explorer.refresh();
					}
				});
			}.bind(this));
			this.close();
		}, function () {
			this.close();
		});
	},
	restore : function(e){
		var _self = this;
		var dataList = this.explorer.selectedList;
		this.app.confirm("warn", e, "恢复文件确认", "是否恢复选中的"+dataList.length+"个文件？", 350, 120, function () {
			var count = 0;
			dataList.each( function(data){


				o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv", {
					"fun": data.type==="folder"?"resumeFolder":"resumeDocument",
					"data": {
						"documentId": data.id,
						"folderId" : data.id
					}
				}, function (json) {
					count++;
					if( dataList.length == count ){
						_self.app.notice("成功恢复"+count+"个文件。");
						_self.explorer.refresh();
					}

				}.bind(this));

			}.bind(this));
			this.close();
		}, function () {
			this.close();
		});
	},
	clear : function (e){
		var _self = this;
		var dataList = this.explorer.selectedList;
		this.app.confirm("warn", e, "清空回收站确认", "是否清空回收站？清空后文件不能恢复。", 350, 120, function () {

			o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv", {
				"fun": "clear",
				"data": {
				}
			}, function (json) {
				_self.explorer.refresh();
			}.bind(this));

			this.close();
		}, function () {
			this.close();
		});
	},
	loadRightNode : function(){
		this.toolabrRightNode = new Element("div.toolabrRightNode",{
			"style": "float:right"
		}).inject(this.node);

		if(this.explorer.isTile){
			this.loadListType();
		}

	},
	getListType : function(){
		return this.viewType || this.options.viewType
	},
	loadListType : function(){

		this.listViewTypeNode = new Element("div", {
			"style" : "font-size:18px;float:left;margin-right:6px",
			"class" : this.options.viewType == "list" ? "mainColor_color" : "",
			events : {
				click : function(){
					this.viewType = "list";

					this.explorer.options.defaultViewType = this.viewType;
					this.explorer.refresh();
				}.bind(this)
			}
		}).inject(this.toolabrRightNode);
		new Element("icon",{"class":"o2Drive icon-list"}).inject(this.listViewTypeNode);

		this.tileViewTypeNode = new Element("div", {
			"style" : "font-size:18px;float:left",
			"class" : this.options.viewType !== "list" ? "mainColor_color" : "",
			events : {
				click : function(){
					this.viewType = "tile";

					this.explorer.options.defaultViewType = this.viewType;
					this.explorer.refresh();
				}.bind(this)
			}
		}).inject(this.toolabrRightNode);
		new Element("icon",{"class":"o2Drive icon-grid"}).inject(this.tileViewTypeNode);
	},

	share : function(){


		if (this.explorer.selectedList && this.explorer.selectedList.length){
			var data = this.explorer.selectedList;
			var form = new MWF.xApplication.OfficeOnline.ShareForm(this.explorer, {}, {
			}, {
				app: this.app
			});
			form.checkedItemData = data;
			form.edit();
		}else {
			this.app.notice("请先选择文件","error");
			return;
		}



	},
	upload : function (){

		var folderId = this.explorer.folderId;

		o2.Actions.get("x_onlyofficefile_assemble_control").action.actions = {};
		o2.Actions.get("x_onlyofficefile_assemble_control").action.actions.upload = {
			"enctype": "formData",
			"method": "POST",
			"uri": "/jaxrs/onlyoffice/upload"
		}


		o2.require("o2.widget.Upload", null, false);
		var upload = new o2.widget.Upload(this.app.content, {
			"action": o2.Actions.get("x_onlyofficefile_assemble_control").action,
			"method": "upload",
			"multiple":false,
			"parameter": {
				"category": "OfficeOnline"
			},
			"data" : {
				"category": "OfficeOnline"
			},
			"accept" : ".doc,.docx,.ppt,.pptx,.xls,.xlsx",
			"onCompleted": function(json){

				console.log(json)

				var documentId = json.id;
				o2.Actions.load("x_onlyofficefile_assemble_control").OnlyofficeAction.get(documentId,function( json ){
					var document = json.data;
					var fileName = document.fileName;

					o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv",{
						"fun" : "createDocument",
						"data" : {
							"fileName": fileName.substr(0,fileName.lastIndexOf(".")),
							"fileType" : document.fileType.replace(".",""),
							"folderId": folderId,
							"teamId" : null,
							"documentId" : documentId,
							"fileSize" : document.fileSize
						}
					},function(json) {
						this.explorer.refresh();
					}.bind(this))


				}.bind(this),null,false );
			}.bind(this)
		});
		upload.load();


	},
	shareDownload : function (){
		var _self = this;
		var data = this.explorer.selectedList[0];

		var url = o2.Actions.getHost( "x_portal_assemble_surface" ) + "/x_OfficeOnline_assemble_control/jaxrs/share/download/share/{shareId}/file/{fileId}";

		debugger
		if(data.fileId){
			url = url.replace("{shareId}", data.id);
			url = url.replace("{fileId}", data.fileId);

		}else {
			url = url.replace("{shareId}", this.explorer.shareId);
			url = url.replace("{fileId}", data.id);
		}


		window.open(o2.filterUrl(url));


	},
	shareShield : function (e){
		var _self = this;
		var dataList = this.explorer.selectedList;
		this.app.confirm("warn", e, "屏蔽分享确认", "屏蔽的分享文件无法恢复！是否屏蔽选中的"+dataList.length+"个文件？", 350, 120, function () {
			var count = 0;
			dataList.each( function(data){
				_self.action.ShareAction.shield( data.id , function(){
					count++;
					if( dataList.length == count ){
						_self.app.notice("成功屏蔽"+count+"个分享文件");
						_self.explorer.refresh();
					}
				});
			}.bind(this));
			this.close();
		}, function () {
			this.close();
		});
	},
	download : function (){

		var _self = this;
		var dataList = this.explorer.selectedList;

		var url = o2.Actions.getHost( "x_onlyofficefile_assemble_control" ) + "/x_onlyofficefile_assemble_control/jaxrs/onlyoffice/file/"+dataList[0].documentId+"/0";

		window.open(o2.filterUrl(url));

	},
});
MWF.xApplication.OfficeOnline.ReNameForm = new Class({
	Extends: MPopupForm,
	Implements: [Options, Events],
	options: {
		"style": "attendanceV2",
		"width": 700,
		//"height": 300,
		"height": "200",
		"hasTop": true,
		"hasIcon": false,
		"draggable": true,
		"title" : "重命名",
		"id" : ""
	},
	_createTableContent: function () {

		var html = "<table width='100%' bordr='0' cellpadding='7' cellspacing='0' styles='formTable' style='margin-top: 20px; '>" +
			"<tr><td styles='formTableTitle' lable='name' width='25%'></td>" +
			"    <td styles='formTableValue14' item='name' colspan='3'></td></tr>" +
			"</table>";
		this.formTableArea.set("html", html);

		this.form = new MForm(this.formTableArea, this.data || {}, {
			isEdited: true,
			style : "minder",
			hasColon : true,
			itemTemplate: {
				name: { text : "名称", notEmpty : true }
			}
		}, this.app);
		this.form.load();

	},
	_createBottomContent: function () {

		if (this.isNew || this.isEdited) {

			this.okActionNode = new Element("button.inputOkButton", {
				"styles": this.css.inputOkButton,
				"text": "确定"
			}).inject(this.formBottomNode);

			this.okActionNode.addEvent("click", function (e) {
				this.save(e);
			}.bind(this));
		}

		this.cancelActionNode = new Element("button.inputCancelButton", {
			"styles": (this.isEdited || this.isNew || this.getEditPermission() ) ? this.css.inputCancelButton : this.css.inputCancelButton_long,
			"text": "关闭"
		}).inject(this.formBottomNode);

		this.cancelActionNode.addEvent("click", function (e) {
			this.close(e);
		}.bind(this));

	},
	save: function(){


		var data = this.form.getResult(true,null,true,false,true);
		if( data ){

			o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv", {
				"fun": data.fileType === "folder"?"renameFolder":"renameDocument",
				"data": {
					"documentId": data.id,
					"folderId" : data.id,
					"name" : data.name
				}
			}, function (json) {
				this.app.notice("重命名成功");
				this.explorer.refresh();
				this.close();

			}.bind(this));

		}
	}
});
MWF.xApplication.OfficeOnline.FolderForm = new Class({
	Extends: MPopupForm,
	Implements: [Options, Events],
	options: {
		style : "attendanceV2",
		"width": 700,
		//"height": 300,
		"height": "200",
		"hasTop": true,
		"hasIcon": false,
		"draggable": true,
		"title" : "新建文件夹"
	},
	_createTableContent: function () {

		var html = "<table width='100%' bordr='0' cellpadding='7' cellspacing='0' styles='formTable' style='margin-top: 20px; '>" +
			"<tr><td styles='formTableTitle' lable='name' width='25%'></td>" +
			"    <td styles='formTableValue14' item='name' colspan='3'></td></tr>" +
			"</table>";
		this.formTableArea.set("html", html);

		this.form = new MForm(this.formTableArea, this.data || {}, {
			isEdited: true,
			style : "minder",
			hasColon : true,
			itemTemplate: {
				name: { text : "名称", notEmpty : true }
			}
		}, this.app);
		this.form.load();

	},
	_createBottomContent: function () {

		if (this.isNew || this.isEdited) {

			this.okActionNode = new Element("button.inputOkButton", {
				"styles": this.css.inputOkButton,
				"text": "确定"
			}).inject(this.formBottomNode);

			this.okActionNode.addEvent("click", function (e) {
				this.save(e);
			}.bind(this));
		}

		this.cancelActionNode = new Element("button.inputCancelButton", {
			"styles": (this.isEdited || this.isNew || this.getEditPermission() ) ? this.css.inputCancelButton : this.css.inputCancelButton_long,
			"text": "关闭"
		}).inject(this.formBottomNode);

		this.cancelActionNode.addEvent("click", function (e) {
			this.close(e);
		}.bind(this));

	},
	save: function(){
		var data = this.form.getResult(true,null,true,false,true);
		if( data ){

			o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv", {
				"fun": "createFolder",
				"data": {
					"name": data.name,
					"parentId": this.explorer.folderId,

				}
			}, function (json) {
				this.explorer.refresh();
				this.close();

			}.bind(this));

		}
	}
});
MWF.xApplication.OfficeOnline.OfficeForm = new Class({
	Extends: MPopupForm,
	Implements: [Options, Events],
	options: {
		style : "attendanceV2",
		"width": 700,
		//"height": 300,
		"height": "200",
		"hasTop": true,
		"hasIcon": false,
		"draggable": true,
		"title" : "新建在线文档"
	},
	_createTableContent: function () {

		var html = "<table width='100%' bordr='0' cellpadding='7' cellspacing='0' styles='formTable' style='margin-top: 20px; '>" +
			"<tr><td styles='formTableTitle' lable='name' width='25%'></td>" +
			"    <td styles='formTableValue14' item='name' width='50%'></td>" +
			"    <td styles='formTableValue14' item='type' width='25%'></td>" +
			"</tr>" +
			"</table>";
		this.formTableArea.set("html", html);

		this.form = new MForm(this.formTableArea, this.data || {}, {
			isEdited: true,
			style : "minder",
			hasColon : true,
			itemTemplate: {
				name: { text : "名称", notEmpty : true },
				type: {
					"text": "类型",
					"type": "select",
					"style": {"min-width": "100px"},
					"selectText": ["", "Word","Excel", "PPT"],
					"selectValue": ["", "docx","xlsx", "pptx"],
					"notEmpty" : true
				}
			}
		}, this.app);
		this.form.load();

	},
	_createBottomContent: function () {

		if (this.isNew || this.isEdited) {

			this.okActionNode = new Element("button.inputOkButton", {
				"styles": this.css.inputOkButton,
				"text": "确定"
			}).inject(this.formBottomNode);

			this.okActionNode.addEvent("click", function (e) {
				this.save(e);
			}.bind(this));
		}

		this.cancelActionNode = new Element("button.inputCancelButton", {
			"styles": (this.isEdited || this.isNew || this.getEditPermission() ) ? this.css.inputCancelButton : this.css.inputCancelButton_long,
			"text": "关闭"
		}).inject(this.formBottomNode);

		this.cancelActionNode.addEvent("click", function (e) {
			this.close(e);
		}.bind(this));

	},
	save: function(){
		var data = this.form.getResult(true,null,true,false,true);
		if( data ){
			data.folderId = this.explorer.folderId;

			o2.Actions.load("x_program_center").InvokeAction.execute("officeOnlineSrv", {
				"fun": "createDocument",
				"data": {
					"fileName": data.name,
					"folderId": this.explorer.folderId,
					"fileType" : data.type
				}
			}, function (json) {
				this.explorer.refresh();
				this.close();

			}.bind(this));

			// this.explorer.action["Attachment3Action"].createOfficeFile( data.folderId,data.name + "." + data.type, {},function( json ){
			// 	this.explorer.refresh();
			// 	this.close();
			// }.bind(this));
		}
	}
});
MWF.xApplication.OfficeOnline.ShareForm = new Class({
	Extends: MPopupForm,
	Implements: [Options, Events],
	options: {
		style : "attendanceV2",
		"width": 700,
		//"height": 300,
		"height": "400",
		"hasTop": true,
		"hasIcon": false,
		"draggable": true,
		"title" : "网盘分享"
	},
	_createTableContent: function () {

		var html = "<table width='100%' bordr='0' cellpadding='7' cellspacing='0' styles='formTable' style='margin-top: 20px; '>" +
			"<tr><td styles='formTableTitle' lable='fileName' width='18%'></td>" +
			"    <td styles='formTableValue14' item='fileName'></td></tr>" +
			"<tr><td styles='formTableTitle' lable='shareTo' width='18%'></td>" +
			"    <td styles='formTableValue14' item='shareTo'></td></tr>" +
			"<tr><td styles='formTableTitle' width='18%'></td>" +
			"    <td styles='formTableValue14'>分享文件给其他人</td></tr>" +
			"</table>";
		this.formTableArea.set("html", html);

		this.form = new MForm(this.formTableArea, this.data || {}, {
			isEdited: true,
			style : "minder",
			hasColon : true,
			itemTemplate: {
				fileName : { text : "文件名称", type : "innerHTML", value : function(){
						var name = [];
						this.checkedItemData.each( function(d){
							name.push(d.name );
						});
						return name.join("<br>");
					}.bind(this)},
				shareTo: { type : "org", orgType:["person","unit","group"],text : "分享对象", notEmpty : true, count : 0, style : {
						"min-height" : "100px"
					} }
			}
		}, this.app);
		this.form.load();

	},
	_createBottomContent: function () {

		if (this.isNew || this.isEdited) {

			this.okActionNode = new Element("button.inputOkButton", {
				"styles": this.css.inputOkButton,
				"text": "确定"
			}).inject(this.formBottomNode);

			this.okActionNode.addEvent("click", function (e) {
				this.share(e);
			}.bind(this));
		}

		this.cancelActionNode = new Element("button.inputCancelButton", {
			"styles": (this.isEdited || this.isNew || this.getEditPermission() ) ? this.css.inputCancelButton : this.css.inputCancelButton_long,
			"text": "关闭"
		}).inject(this.formBottomNode);

		this.cancelActionNode.addEvent("click", function (e) {
			this.close(e);
		}.bind(this));

	},
	share: function(){
		var data = this.form.getResult(true,null,true,false,true);
		if( data ){
			var json = {
				shareType : "member",
				shareUserList : [],
				shareOrgList : [],
				shareGroupList : []
			};
			data.shareTo.each( function( s ){
				var flag = s.substr(s.length-1, 1);
				switch (flag.toLowerCase()){
					case "p":
						json.shareUserList.push( s );
						break;
					case "u":
						json.shareOrgList.push( s );
						break;
					case "g":
						json.shareGroupList.push( s );
						break;
					default :
						break;
				}
			}.bind(this));
			var count = 0;



			debugger
			this.checkedItemData.each( function(d){
				json.fileId = d.id;
				this.app.action.ShareAction.create( json, function(){
					count++;
					if( count ==  this.checkedItemData.length){
						this.app.notice( "分享成功！" );
						this.close();
					}
				}.bind(this));
			}.bind(this));
		}
	}
});
MWF.xApplication.OfficeOnline.Util = new Class({
	getFileSize : function( size ){
		if (!size)
			return "-";
		var num = 1024.00; //byte
		if (size < num)
			return size + "B";
		if (size < Math.pow(num, 2))
			return (size / num).toFixed(2) + "K"; //kb
		if (size < Math.pow(num, 3))
			return (size / Math.pow(num, 2)).toFixed(2) + "M"; //M
		if (size < Math.pow(num, 4))
			return (size / Math.pow(num, 3)).toFixed(2) + "G"; //G
		return (size / Math.pow(num, 4)).toFixed(2) + "T";
	},
	randChar : function( length ){
		var characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
		characters = characters.split("");
		var result = "";
		while (result.length < length) result += characters[Math.floor(Math.random() * characters.length)];
		return result;
	},
	getFileExtension : function(extension){

		var extensionObj = {
			"folder" : ["folder"],
			"excel":["xls","xlsx"],
			"exe":["exe"],
			"js":["js"],
			"folder":["folder"],
			"html":["html"],
			"css":["css"],
			"word":["doc","docx"],
			"file":["md","conf"],
			"img":["bmp", "gif", "png", "jpeg", "jpg", "jpe", "ico","svg"],
			"ppt":["ppt","pptx"],
			"rar":["rar","7z","zip"],
			"music":["mp3", "wav", "wma"],
			"txt":["txt"],
			"pdf":["pdf"],
			"vedio":["avi", "mkv", "mov", "ogg", "mp4", "mpa", "mpe", "mpeg", "mpg", "rmvb", "wmv"]
		};
		for (var key in extensionObj){
			if (extensionObj[key].contains(extension)) {
				return key;
			}
		}
		return "other";
	}
});
