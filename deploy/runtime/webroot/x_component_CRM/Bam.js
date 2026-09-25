
MWF.xApplication.CRM = MWF.xApplication.CRM || {};
MWF.xDesktop.requireApp("CRM", "Common", null, false);

MWF.xApplication.CRM.Bam = new Class({
    Extends: MWF.widget.Common,
    Implements: [Options, Events],
    options: {
        "style": "default"
    },
    initialize: function (container, app, data, options) {
        this.setOptions(options);
        this.container = container;

        this.app = app;
        this.lp = this.app.lp.bam;
        this.actions = this.app.actions;

        this.path = "/x_component_CRM/$Bam/";
        this.cssPath = this.path+this.options.style+"/css.wcss";
        this._loadCss();

        this.data = data;
    },
    load: function () {
        this.container.empty();
        this.createTopBarLayout();
        this.createContainerLayout();
    },
    createTopBarLayout:function(){
        var _self = this;
        this.topBarLayout = new Element("div.topBarLayout",{styles:this.css.topBarLayout}).inject(this.container);
        this.topBarBackContainer = new Element("div.topBarBackContainer",{styles:this.css.topBarBackContainer}).inject(this.topBarLayout);
        this.topBarBackHomeIcon = new Element("div.topBarBackHomeIcon",{styles:this.css.topBarBackHomeIcon}).inject(this.topBarBackContainer);
        this.topBarBackHomeIcon.addEvents({
            click:function(){
                window.location.reload();
            }.bind(this),
        });
        debugger;
        this.topBarBackHomeNext = new Element("div.topBarBackHomeNext",{styles:this.css.topBarBackHomeNext}).inject(this.topBarBackContainer);
        this.bamTitle = new Element("div.bamTitle",{styles:this.css.bamTitle,text:this.lp.title}).inject(this.topBarBackContainer);
    },
    createContainerLayout: function(){
        this.containerLayout = new Element("div.containerLayout",{styles:this.css.containerLayout}).inject(this.container);
        this.createNaviLayout();
        this.createContentLayout();
        this.templateDiv.click();
    },

    createNaviLayout:function(){
        var _self = this;
        this.naviLayout = new Element("div.naviLayout",{styles:this.css.naviLayout}).inject(this.containerLayout);

        new Element("div.naviMenu",{styles:this.css.naviMenu, text:this.lp.base}).inject(this.naviLayout);

        //模板管理
        this.templateDiv = new Element("div.templateDiv",{styles:this.css.naviItem}).inject(this.naviLayout);
        this.templateDiv.addEvents({
            mouseenter:function(){
                if(this.curNavi == this.templateDiv) return;
                this.templateDiv.setStyles({"border-left":"2px solid #1b9aee","color":"#000000"});
            }.bind(this),
            mouseleave:function(){
                if(this.curNavi == this.templateDiv) return;
                this.templateDiv.setStyles({"border-left":"2px solid #ffffff","color":"#595959"});
            }.bind(this),
            click:function(){
                if(this.curNavi)this.curNavi.setStyles({"border-left":"2px solid #ffffff","color":"#595959"});
                this.curNavi = this.templateDiv;
                this.curNavi.setStyles({"border-left":"2px solid #0171c2","color":"#000000"});
                this.createTemplateLayout();
            }.bind(this)
        });
        new Element("div.templateIcon",{ styles: this.css.templateIcon }).inject(this.templateDiv);
        new Element("div.templateText",{styles: this.css.templateText, text: this.lp.config}).inject(this.templateDiv);

    },
    createContentLayout:function(){
        this.contentLayout = new Element("div.contentLayout",{styles:this.css.contentLayout}).inject(this.containerLayout);
    },
    createPriorityLayout:function(){
        var _self = this;
        this.contentLayout.empty();

        var priorityTop = new Element("div.priorityTop",{styles:this.css.priorityTop}).inject(this.contentLayout);
        var priorityTopContent = new Element("div.priorityTopContent",{styles:this.css.priorityTopContent}).inject(priorityTop);
        var priorityTopTitle = new Element("div.priorityTopTitle",{styles:this.css.priorityTopTitle,text:this.lp.priority.title}).inject(priorityTopContent);
        var priorityTopDes = new Element("div.priorityTopDes",{styles:this.css.priorityTopDes,text:this.lp.priority.tips}).inject(priorityTopContent);

        // var templateTopAddContent = new Element("div.templateTopAddContent",{styles:this.css.templateTopAddContent}).inject(templateTop);
        // var templateTopAdd = new Element("div.templateTopAdd",{styles:this.css.templateTopAdd,text:this.lp.template.add}).inject(templateTopAddContent);
        // templateTopAdd.addEvents({
        //     mouseover:function(){
        //         this.setStyles({"color":"#0171c2"})
        //     },
        //     mouseout:function(){
        //         this.setStyles({"color":"#1b9aee"})
        //     },
        //     click:function(){
        //         _self.openTemplate();
        //     }
        // });

        var priorityContainer = new Element("div.priorityContainer",{styles:this.css.priorityContainer}).inject(this.contentLayout);
        this.priorityItemContent = new Element("div.priorityItemContent",{styles:this.css.priorityItemContent}).inject(priorityContainer);
        this.app.setLoading(this.priorityItemContent);
        this.rootActions.GlobalAction.priorityList(function(json){
            this.priorityItemContent.empty();
            json.data.each(function(data){
                this.createPriorityItem(data);
            }.bind(this))
        }.bind(this))

        var addPriorityContainer = new Element("div.addPriorityContainer",{styles:this.css.addPriorityContainer}).inject(priorityContainer,"bottom");
        var addPriorityIcon = new Element("div.addPriorityIcon",{styles:this.css.addPriorityIcon}).inject(addPriorityContainer);
        var addPriorityTxt = new Element("div.addPriorityTxt",{styles:this.css.addPriorityTxt, text: this.lp.priority.add}).inject(addPriorityContainer);
        addPriorityContainer.addEvents({
            mouseenter:function(){
                addPriorityIcon.setStyles({"background-image":"url(/x_component_CRM/$Bam/default/icon/icon_add_click.png)"});
                addPriorityTxt.setStyles({"color":"#13227a"})
            },
            mouseleave:function(){
                addPriorityIcon.setStyles({"background-image":"url(/x_component_CRM/$Bam/default/icon/icon_add.png)"});
                addPriorityTxt.setStyles({"color":"#1296db"})
            },
            click:function(){ //fffffffff
                this.createPriorityItem();
            }.bind(this)
        })
    },
    createPriorityColorItem:function(content,data,vColor,bColor){

        var priorityColorItem = new Element("div.priorityColorItem",{styles:this.css.priorityColorItemContainer}).inject(content);
        var priorityColor = new Element("div.priorityColor",{styles:this.css.priorityColor}).inject(priorityColorItem);
        priorityColor.setStyles({"background-color":vColor});

        if(data && data.priorityColor.toUpperCase() == bColor.toUpperCase()){
            priorityColor.setStyles({
                "width":"18px",
                "height":"18px",
                "background-color":bColor,
                "border":"3px solid " + vColor + " "
            });
            priorityColor.set("name","active");
        }

        priorityColor.addEvents({
            mouseover:function(){
                if(this.get("name")=="active") return;
                this.setStyles({"background-color":bColor ,"width":"18px","height":"18px"});
            },
            mouseout:function(){
                if(this.get("name")=="active") return;
                this.setStyles({"background-color":vColor,"width":"14px","height":"14px"});
            },
            click:function(){
                if(this.get("name")=="active") return;
                var actName = content.getElements("div[name='active']");
                if(actName.length>0){
                    actName[0].removeProperty("name");
                    var color = actName[0].getStyle("border-left-color");
                    actName[0].setStyles({
                        "border":"0px",
                        "width":"14px",
                        "height":"14px",
                        "background-color":color
                    });
                }

                this.set("name","active");
                this.setStyles({
                    "width":"18px",
                    "height":"18px",
                    "background-color": bColor,
                    "border":"3px solid " + vColor
                });

            }
        });

    },
    createPriorityItem:function(data){
        var _self = this;
        var id = data ? data.id : "";
        var priorityItemContainer = new Element("div.priorityItemContainer",{styles:this.css.priorityItemContainer,index:data ? data.order:""}).inject(this.priorityItemContent);
        //var priorityItemMove = new Element("div.priorityItemMove",{styles:this.css.priorityItemMove}).inject(priorityItemContainer);

        var priorityValueContainer = new Element("div.priorityValueContainer",{styles:this.css.priorityValueContainer}).inject(priorityItemContainer);
        var priorityValue = new Element("input",{styles:this.css.priorityValue,type:"input",value:data?data.priority:""}).inject(priorityValueContainer);
        priorityValue.addEvents({
            blur:function(){
                if(this.get("value").trim()=="") this.setStyles({"border":"1px solid #ff0000"});
                else this.setStyles({"border":"1px solid #cccccc"});
            },
            focus:function(){
                this.setStyles({"border":"1px solid #1296db"})
            },
            keyup:function(){
                var v = this.get("value").trim();
                if(v=="") this.setStyles({"border":"1px solid #ff0000"})
                else this.setStyles({"border":"1px solid #1296db"})
            }
        });
        var priorityColorContainer = new Element("div.priorityColorContainer",{styles:this.css.priorityColorContainer}).inject(priorityItemContainer);

        // red
        this.createPriorityColorItem(priorityColorContainer, data,"#FFCCCC", "#E62412");
        // orange
        this.createPriorityColorItem(priorityColorContainer, data,"#FFD591", "#FA8C15");
        // green
        this.createPriorityColorItem(priorityColorContainer, data,"#CAFAC8", "#15AD31");
        // blue
        this.createPriorityColorItem(priorityColorContainer, data,"#CCECFF", "#1B9AEE");
        // grey
        this.createPriorityColorItem(priorityColorContainer, data,"#E5E5E5", "#8C8C8C");


        //actions
        var priorityActionContainer = new Element("div.priorityActionContainer",{styles:this.css.priorityActionContainer}).inject(priorityItemContainer);
        var priorityActionOK = new Element("div.priorityActionOK",{styles:this.css.priorityActionOK}).inject(priorityActionContainer);
        priorityActionOK.addEvents({
            mouseover:function(){
                this.setStyles({"background-image":"url(/x_component_CRM/$Bam/default/icon/icon_ok_click.png)"})
            },
            mouseout:function(){
                this.setStyles({"background-image":"url(/x_component_CRM/$Bam/default/icon/icon_ok.png)"})
            },
            click:function(){
                var colorObj = priorityColorContainer.getElements("div[name='active']");
                if(priorityValue.get("value").trim()==""){
                    priorityValue.setStyles({"border":"1px solid #ff0000"});
                    window.setTimeout(function(){
                        priorityValue.setStyles({"border":"1px solid #cccccc"});
                        window.setTimeout(function(){
                            priorityValue.setStyles({"border":"1px solid #ff0000"});
                        },200)
                    },200);
                    return;
                }
                if(colorObj.length == 0){
                    //priorityColorContainer.setStyles({"border":"1px solid #ff0000"});
                    var objs = priorityColorContainer.getElements(".priorityColorItem");
                    objs.each(function(obj,i){
                        var time = (i + 1) * 50;
                        window.setTimeout(function(){
                            //obj.setStyles({"width":"18px","height":"18px"});
                            obj.setStyles({"background-color":"#ff0000"});
                            window.setTimeout(function(){
                                //obj.setStyles({"width":"14px","height":"14px"});
                                obj.setStyles({"background-color":""});
                            },50);
                        },time)
                    })
                    return;
                }

                var data = {
                    id:id,
                    priority:priorityValue.get("value").trim(),
                    priorityColor:colorObj[0].getStyle("background-color"),
                    order:priorityItemContainer.get("index")
                };

                this.rootActions.GlobalAction.prioritySave(data,function(json){
                    id = json.data.id
                    this.app.notice(this.lp.priority.success,"success")
                }.bind(this))

            }.bind(this)
        });
        var priorityActionRemove = new Element("div.priorityActionRemove",{styles:this.css.priorityActionRemove}).inject(priorityActionContainer);
        priorityActionRemove.addEvents({
            mouseover:function(){
                this.setStyles({"background-image":"url(/x_component_CRM/$Bam/default/icon/icon_close_click.png)"})
            },
            mouseout:function(){
                this.setStyles({"background-image":"url(/x_component_CRM/$Bam/default/icon/icon_close.png)"})
            },
            click:function(e){
                if(id==""){
                    var fx = new Fx.Tween(priorityItemContainer,{duration:200});
                    fx.start(["height"] ,"60px", "0px").chain(function(){
                        priorityItemContainer.destroy();
                    }.bind(this));
                    //priorityItemContainer.destroy();
                }else{
                    _self.app.confirm("warn",e,_self.app.lp.common.confirm.removeTitle,_self.app.lp.common.confirm.removeContent,300,120,function(){
                        _self.rootActions.GlobalAction.priorityDelete(id,function(){
                            var fx = new Fx.Tween(priorityItemContainer,{duration:200});
                            fx.start(["height"] ,"60px", "0px").chain(function(){
                                priorityItemContainer.destroy();
                                this.close();
                            }.bind(this));


                            //priorityItemContainer.destroy();
                            //this.close();
                        }.bind(this))
                    },function(){
                        this.close();
                    });
                }
            }
        });
        return;
    },
    createTemplateLayout:function(){
        var _self = this;
        this.contentLayout.empty();
        var templateTop = new Element("div.templateTop",{styles:this.css.templateTop}).inject(this.contentLayout);
        var templateTopContent = new Element("div.templateTopContent",{styles:this.css.templateTopContent}).inject(templateTop);
        var templateTopTitle = new Element("div.templateTopTitle",{styles:this.css.templateTopTitle,text:this.lp.title}).inject(templateTopContent);
        var templateTopDes = new Element("div.templateTopDes",{styles:this.css.templateTopDes,text:this.lp.tips}).inject(templateTopContent);

        var viewSearchContainer = new Element("div.viewSearchContainer",{styles:this.css.viewSearchContainer,text:""}).inject(templateTopContent);
        var viewSearchContent = new Element("div.viewSearchContent",{styles:this.css.viewSearchContent}).inject(viewSearchContainer);

        var viewConfigModule = new Element("div.viewSearchModule",{styles:this.css.viewSearchModule}).inject(viewSearchContent);
        var viewConfigModuleItem = new Element("div.viewSearchItem",{styles:this.css.viewSearchItem,text:this.lp.template.module+"："}).inject(viewConfigModule);
        var viewConfigModuleInput =  new Element("input.viewSearchInput",{styles:this.css.viewSearchInput,"name":"configModuleInput"}).inject(viewConfigModule);

        var viewConfigType = new Element("div.viewSearchModule",{styles:this.css.viewSearchModule}).inject(viewSearchContent);
        var viewConfigTypeItem = new Element("div.viewSearchItem",{styles:this.css.viewSearchItem,text:this.lp.template.configType+"："}).inject(viewConfigType);
        var viewConfigTypeInput =  new Element("input.viewSearchInput",{styles:this.css.viewSearchInput,"name":"configTypeInput"}).inject(viewConfigType);

        var viewConfigName = new Element("div.viewSearchModule",{styles:this.css.viewSearchModule}).inject(viewSearchContent);
        var viewConfigNameItem = new Element("div.viewSearchItem",{styles:this.css.viewSearchItem,text:this.lp.template.configName+"："}).inject(viewConfigName);
        var viewConfigNameInput =  new Element("input.viewSearchInput",{styles:this.css.viewSearchInput,"name":"configNameInput"}).inject(viewConfigName);

        var viewConfigCode = new Element("div.viewSearchModule",{styles:this.css.viewSearchModule}).inject(viewSearchContent);
        var viewConfigCodeItem = new Element("div.viewSearchItem",{styles:this.css.viewSearchItem,text:this.lp.template.configCode+"："}).inject(viewConfigCode);
        var viewConfigCodeInput =  new Element("input.viewSearchInput",{styles:this.css.viewSearchInput,"name":"configCodeInput"}).inject(viewConfigCode);

        var fileData = {
            "orderField":"orderNumber",
            "orderType":"ASC"
        };

        var viewSearchSearch = new Element("div",{styles:this.css.viewSearchSearch}).inject(viewSearchContent);
        this.viewSearchSearch = viewSearchSearch;
        viewSearchSearch.addEvents({
            click:function(){
                if(viewConfigModuleInput.get("value").trim()=="" && viewConfigTypeInput.get("value").trim()=="" && viewConfigNameInput.get("value").trim()=="" && viewConfigCodeInput.get("value").trim()=="") return;
                viewSearchReset.show();
                fileData = {
                    "configModule":viewConfigModuleInput.get("value"),
                    "configType":viewConfigTypeInput.get("value"),
                    "configName":viewConfigNameInput.get("value"),
                    "configCode":viewConfigCodeInput.get("value"),
                    "orderField":"orderNumber",
                    "orderType":"ASC"
                };
                debugger;
                this.loadView(fileData);
            }.bind(this)
        });
        var viewSearchReset = new Element("div",{styles:this.css.viewSearchReset}).inject(viewSearchContent);
        viewSearchReset.addEvents({
            click:function(){
                viewSearchReset.hide();
                viewConfigModuleInput.set("value","");
                viewConfigTypeInput.set("value","");
                viewConfigNameInput.set("value","");
                viewConfigCodeInput.set("value","");
                fileData = {
                    "orderField":"orderNumber",
                    "orderType":"ASC"
                };
                this.loadView(fileData);
            }.bind(this)
        });
        debugger;

        var templateTopAddContent = new Element("div.templateTopAddContent",{styles:this.css.templateTopAddContent}).inject(templateTop);
        var templateTopAdd = new Element("div.templateTopAdd",{styles:this.css.templateTopAdd,text:this.lp.add}).inject(templateTopAddContent);
        templateTopAdd.addEvents({
            mouseover:function(){
                this.setStyles({"color":"#0171c2"})
            },
            mouseout:function(){
                this.setStyles({"color":"#1b9aee"})
            },
            click:function(){
                _self.openTemplate();
            }
        });
        this.templateContainer = new Element("div.templateContainer",{styles:this.css.templateContainer}).inject(this.contentLayout);
        fileData = {
            "configModule":viewConfigModuleInput.get("value"),
            "configType":viewConfigTypeInput.get("value"),
            "configName":viewConfigNameInput.get("value"),
            "configCode":viewConfigCodeInput.get("value"),
            "orderField":"orderNumber",
            "orderType":"ASC"
        };
        this.loadView(fileData);
    },
    loadView:function(fileData){
        debugger
        this.actions.listConfigNextWithFilter("(0)",100,fileData,function(json){
            debugger;
            this.templateContainer.empty();
            if(json.count>0){
                json.data.each(function(data){
                    this.createTemplateItem(data);
                }.bind(this))
            }
        }.bind(this))
    },
    createTemplateItem:function(data){
        var _self = this;
        debugger;
        var templateItemContainer = new Element("div.templateItemContainer",{ styles:this.css.templateItemContainer }).inject(this.templateContainer);
        templateItemContainer.addEvents({
            mouseenter:function(){
                templateItemContainer.setStyles({"background-color":"rgb(242,245,247)"});
            }.bind(this),
            mouseleave:function(){
                templateItemContainer.setStyles({"background-color":""});
            }.bind(this),
            click:function(){
                // this.openTemplate(data.id)
            }.bind(this)
        });


        var templateItemLane = new Element("div.templateItemLane",{styles:this.css.templateItemLane}).inject(templateItemContainer);
        var templateItemLaneTxt = new Element("div.configModule",{styles:this.css.templateItemLaneTxt,text:data.configModule}).inject(templateItemLane);

        var templateItemType = new Element("div.configType",{styles:this.css.templateItemType,text:data.configType}).inject(templateItemContainer);

        var templateItemContent = new Element("div.templateItemContent",{styles:this.css.templateItemContent}).inject(templateItemContainer);
        var templateItemTitle = new Element("div.templateItemTitle",{styles:this.css.templateItemTitle,text:data.configName}).inject(templateItemContent);
        var templateItemDes = new Element("div.templateItemDes",{styles:this.css.templateItemDes,text:data.configCode==""?"无":data.configCode}).inject(templateItemContent);

        var templateItemSource = new Element("div.configType",{styles:this.css.templateItemSource,text:data.description}).inject(templateItemContainer);

        var templateItemDate = new Element("div.templateItemDate",{styles:this.css.templateItemDate,text:data.updateTime.split(" ")[0]}).inject(templateItemContainer);

        var templateItemOrderNumber = new Element("div.configType",{styles:this.css.templateItemOrderNumber,text:data.orderNumber}).inject(templateItemContainer);

        var templateItemActionContainer = new Element("div.templateItemActionContainer",{styles:this.css.templateItemActionContainer}).inject(templateItemContainer);
        var templateItemEdit = new Element("div.templateItemEdit",{ styles:this.css.templateItemEdit,text:this.lp.edit }).inject(templateItemActionContainer);
        templateItemEdit.addEvents({
            click:function(){
                this.openTemplate(data.id)
            }.bind(this)
        });
        var templateItemRemove = new Element("div.templateItemRemove",{ styles:this.css.templateItemRemove,text:this.lp.remove }).inject(templateItemActionContainer);
        templateItemRemove.addEvents({
            click:function(e){
                _self.app.confirm("warn",e,_self.lp.removeTitle,_self.lp.removeContent,300,120,function(){
                    _self.actions.deleteConfig(data.id,function(){
                        _self.createTemplateLayout();
                        this.close();
                    }.bind(this))
                },function(){
                    this.close();
                });
            }
        });

    },
    openTemplate:function(id){
        var data = {
            id:id || ""
        }
        MWF.xDesktop.requireApp("CRM", "Config", function(){
            this.np = new MWF.xApplication.CRM.Config(this,data,
                {"width": 500,"height": 950,
                    onPostOpen:function(){
                        this.np.formAreaNode.setStyles({"top":"10px","position":"absolute"});
                        this.np.formNode.setStyles({"background-color":"rgb(255, 255, 255)","box-shadow":"rgb(153, 153, 153) 0px 0px 10px","border-radius":"5px","border":"1px solid rgb(255, 255, 255)","margin":"auto"});
                        this.np.formContentNode.setStyles({"border":"0px solid rgb(102, 102, 102)","width":"100%","margin":"auto","color":"rgb(102, 102, 102)","font-size":"14px"});
                        this.np.formTableContainer.setStyles({"margin":"0px 10px","overflow":"scroll"});
                        /*var fx = new Fx.Tween(this.np.formAreaNode,{duration:200});
                        fx.start(["top"] ,"10px", "100px");*/

                    }.bind(this),
                    onPostClose:function(json){
                        if(json){
                            this.viewSearchSearch.click();
                        }
                    }.bind(this)
                }
            );
            this.np.open();
        }.bind(this));

    }
});
