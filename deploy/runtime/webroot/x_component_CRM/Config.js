MWF.xApplication.CRM = MWF.xApplication.CRM || {};
MWF.xApplication.CRM.Config = new Class({
    Extends: MWF.xApplication.CRM.Common.Popup,
    options: {
        "closeByClickMask": false
    },
    open: function (e) {
        //设置css 和 lp等
        var css = this.css;
        this.cssPath = "/x_component_CRM/$Config/" + this.options.style + "/css.wcss";
        this._loadCss();
        if (css) this.css = Object.merge(css, this.css);

        this.lp = this.app.lp.bam.template;


        this.fireEvent("queryOpen");
        this.isNew = false;
        this.isEdited = false;
        this._open();
        this.fireEvent("postOpen");
    },

    _createTableContent: function () {
        debugger
        var _self = this;
        if(this.data.id!=""){
            this.isEdited = true
        }else{
            this.isEdited = false;
        }
        var topTitleContainer = new Element("div.topTitleContainer",{styles:this.css.topTitleContainer}).inject(this.formTableArea);
        var topTitle = new Element("div.topTitle",{styles:this.css.topTitle,text:this.lp.title}).inject(topTitleContainer);
        //所属模块
        var templateModuleTxt = new Element("div.templateModuleTxt",{styles:this.css.templateNameTxt,text:this.lp.module}).inject(this.formTableArea);
        var templateModuleContainer = new Element("div.templateNameContainer",{styles:this.css.templateNameContainer}).inject(this.formTableArea);
        this.templateModuleInput = new Element("input",{type:"text",styles:this.css.templateNameInput,value:""}).inject(templateModuleContainer);
        this.templateModuleInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            blur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            }
        })
        debugger
        //配置类型
        var templateConfigTypeTxt = new Element("div.templateModuleTxt",{styles:this.css.templateNameTxt,text:this.lp.configType}).inject(this.formTableArea);
        var templateConfigTypeContainer = new Element("div.templateNameContainer",{styles:this.css.templateNameContainer}).inject(this.formTableArea);
        this.templateConfigTypeInput = new Element("input",{type:"text",styles:this.css.templateNameInput,value:""}).inject(templateConfigTypeContainer);
        this.templateConfigTypeInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            blur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            }
        })
        //字段名称
        var templateConfigNameTxt = new Element("div.templateNameTxt",{styles:this.css.templateNameTxt,text:this.lp.configName}).inject(this.formTableArea);
        var templateConfigNameContainer = new Element("div.templateNameContainer",{styles:this.css.templateNameContainer}).inject(this.formTableArea);
        this.templateConfigNameInput = new Element("input",{type:"text",styles:this.css.templateNameInput,value:""}).inject(templateConfigNameContainer);
        this.templateConfigNameInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            blur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            }
        })
        //字段编码
        var templateConfigCodeTxt = new Element("div.templateNameTxt",{styles:this.css.templateNameTxt,text:this.lp.configCode}).inject(this.formTableArea);
        var templateConfigCodeContainer = new Element("div.templateNameContainer",{styles:this.css.templateNameContainer}).inject(this.formTableArea);
        this.templateConfigCodeInput = new Element("input",{type:"text",styles:this.css.templateNameInput,value:""}).inject(templateConfigCodeContainer);
        this.templateConfigCodeInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            blur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            }
        })
        //字段值内容
        var templateConfigValueTxt = new Element("div.templateNameTxt",{styles:this.css.templateNameTxt,text:this.lp.configValue}).inject(this.formTableArea);
        var templateConfigValueContainer = new Element("div.templateNameContainer",{styles:this.css.templateNameContainer}).inject(this.formTableArea);
        this.templateConfigValueInput = new Element("input",{type:"text",styles:this.css.templateNameInput,value:""}).inject(templateConfigValueContainer);
        this.templateConfigValueInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            blur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            }
        })
        //值类型
        var templateValueTypeTxt = new Element("div.templateNameTxt",{styles:this.css.templateNameTxt,text:this.lp.valueType}).inject(this.formTableArea);
        var templateValueTypeContainer = new Element("div.templateNameContainer",{styles:this.css.templateNameContainer}).inject(this.formTableArea);
        this.templateValueTypeInput = new Element("input",{type:"text",styles:this.css.templateNameInput,value:""}).inject(templateValueTypeContainer);
        this.templateValueTypeInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            blur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            },
            click:function(){
                var pc = new MWF.xApplication.CRM.Config.SelectType(this.container, this.templateValueTypeInput, this.app, {data:this.lp.valueType}, {
                    css:this.css, lp:this.lp, axis : "y",
                    position : { //node 固定的位置
                        x : "right",
                        y : "middle"
                    },
                    nodeStyles : {
                        "min-width":"150px",
                        "padding":"2px",
                        "border-radius":"5px",
                        "box-shadow":"0px 0px 4px 0px #999999",
                        "z-index" : "201"
                    },
                    onPostLoad:function(){
                        pc.node.setStyles({"opacity":"0","top":(pc.node.getStyle("top").toInt()-6)+"px","left":(pc.node.getStyle("left").toInt()+10)+"px"});
                        var fx = new Fx.Tween(pc.node,{duration:400});
                        fx.start(["opacity"] ,"0", "1");
                    },
                    onClose:function(rd){
                        if(!rd) return;
                        debugger
                        this.templateValueTypeInput.set("value",rd.value)
                        //this.dynamicContent.empty();
                    }.bind(this)
                });
                pc.load();
            }.bind(this)
        })
        debugger
        //可选值，和select配合使用，以‘|’号分隔
        var templateSelectContentTxt = new Element("div.templateNameTxt",{styles:this.css.templateNameTxt,text:this.lp.selectContent}).inject(this.formTableArea);
        var templateSelectContentContainer = new Element("div.templateNameContainer",{styles:this.css.templateNameContainer}).inject(this.formTableArea);
        this.templateSelectContentInput = new Element("input",{type:"text",styles:this.css.templateNameInput,value:""}).inject(templateSelectContentContainer);
        this.templateSelectContentInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            blur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            }
        })
        //是否可以多值
        var templateIsMultipleTxt = new Element("div.templateNameTxt",{styles:this.css.templateNameTxt,text:this.lp.isMultiple}).inject(this.formTableArea);
        var templateIsMultipleContainer = new Element("div.templateNameContainer",{styles:this.css.templateNameContainer}).inject(this.formTableArea);
        this.templateIsMultipleInput = new Element("input",{type:"text",styles:this.css.templateNameInput,value:""}).inject(templateIsMultipleContainer);
        this.templateIsMultipleInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            blur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            },
            click:function(){
                var pc = new MWF.xApplication.CRM.Config.SelectType(this.container, this.templateIsMultipleInput, this.app, {data:this.lp.isMultiple}, {
                    css:this.css, lp:this.lp, axis : "y",
                    position : { //node 固定的位置
                        x : "right",
                        y : "middle"
                    },
                    nodeStyles : {
                        "min-width":"150px",
                        "padding":"2px",
                        "border-radius":"5px",
                        "box-shadow":"0px 0px 4px 0px #999999",
                        "z-index" : "201"
                    },
                    onPostLoad:function(){
                        pc.node.setStyles({"opacity":"0","top":(pc.node.getStyle("top").toInt()-6)+"px","left":(pc.node.getStyle("left").toInt()+10)+"px"});
                        var fx = new Fx.Tween(pc.node,{duration:400});
                        fx.start(["opacity"] ,"0", "1");
                    },
                    onClose:function(rd){
                        if(!rd) return;
                        debugger
                        this.templateIsMultipleInput.set("value",rd.value)
                        //this.dynamicContent.empty();
                    }.bind(this)
                });
                pc.load();
            }.bind(this)
        })
        //是否可为空值
        var templateNotEmptyTxt = new Element("div.templateNameTxt",{styles:this.css.templateNameTxt,text:this.lp.notEmpty}).inject(this.formTableArea);
        var templateNotEmptyContainer = new Element("div.templateNameContainer",{styles:this.css.templateNameContainer}).inject(this.formTableArea);
        this.templateNotEmptyInput = new Element("input",{type:"text",styles:this.css.templateNameInput,value:""}).inject(templateNotEmptyContainer);
        this.templateNotEmptyInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            blur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            },
            click:function(){
                var pc = new MWF.xApplication.CRM.Config.SelectType(this.container, this.templateNotEmptyInput, this.app, {data:this.lp.notEmpty}, {
                    css:this.css, lp:this.lp, axis : "y",
                    position : { //node 固定的位置
                        x : "right",
                        y : "middle"
                    },
                    nodeStyles : {
                        "min-width":"150px",
                        "padding":"2px",
                        "border-radius":"5px",
                        "box-shadow":"0px 0px 4px 0px #999999",
                        "z-index" : "201"
                    },
                    onPostLoad:function(){
                        pc.node.setStyles({"opacity":"0","top":(pc.node.getStyle("top").toInt()-6)+"px","left":(pc.node.getStyle("left").toInt()+10)+"px"});
                        var fx = new Fx.Tween(pc.node,{duration:400});
                        fx.start(["opacity"] ,"0", "1");
                    },
                    onClose:function(rd){
                        if(!rd) return;
                        debugger
                        this.templateNotEmptyInput.set("value",rd.value)
                        //this.dynamicContent.empty();
                    }.bind(this)
                });
                pc.load();
            }.bind(this)
        })
        //排序号
        var templateOrderNumberTxt = new Element("div.templateNameTxt",{styles:this.css.templateNameTxt,text:this.lp.orderNumber}).inject(this.formTableArea);
        var templateOrderNumberContainer = new Element("div.templateNameContainer",{styles:this.css.templateNameContainer}).inject(this.formTableArea);
        this.templateOrderNumberInput = new Element("input",{type:"text",styles:this.css.templateNameInput,value:""}).inject(templateOrderNumberContainer);
        this.templateOrderNumberInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            blur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            }
        })

        debugger


        var templateDesTxt = new Element("div.templateDesTxt",{styles:this.css.templateDesTxt,text:this.lp.description}).inject(this.formTableArea);
        var templateDesContainer = new Element("div.templateDesContainer",{styles:this.css.templateDesContainer}).inject(this.formTableArea);
        this.templateDesInput = new Element("textarea.templateDesInput",{styles:this.css.templateDesInput}).inject(templateDesContainer);
        this.templateDesInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            }
        })
        /*var templateLaneTxt = new Element("div.templateLaneTxt",{styles:this.css.templateLaneTxt,text:this.lp.lane+"("+this.lp.laneTip+")"}).inject(this.formTableArea);
        var templateLaneContainer = new Element("div.templateLaneContainer",{styles:this.css.templateLaneContainer}).inject(this.formTableArea);
        this.templateLaneInput = new Element("input",{type:"text",styles:this.css.templateLaneInput,value:"",placeholder:this.lp.laneTip}).inject(templateLaneContainer);
        this.templateLaneInput.addEvents({
            focus:function(){
                this.setStyles({"border":"1px solid #1b9aee"});
            },
            getTemplateblur:function(){
                if(this.get("value").trim()==""){
                    this.setStyles({"border":"1px solid #ff0000"});
                }else{
                    this.setStyles({"border":"1px solid #cccccc"});
                }
            }
        })*/
        debugger
        var templateActionContainer = new Element("div.templateActionContainer",{styles:this.css.templateActionContainer}).inject(this.formTableArea);
        this.closeAction = new Element("div.okAction",{styles:this.css.closeAction,text:this.lp.close}).inject(templateActionContainer);
        this.closeAction.addEvent("click",function(){ this.close(); }.bind(this))
        this.okAction = new Element("div.okAction",{styles:this.css.okAction,text:this.lp.ok}).inject(templateActionContainer);
        this.okAction.addEvents({
            click:function(){
                var flag = true;
                if(this.templateConfigNameInput.get("value").trim()==""){
                    this.templateConfigNameInput.setStyles({"border":"1px solid #ff0000"});
                    flag = false;
                }
                if(this.templateConfigCodeInput.get("value").trim()==""){
                    this.templateConfigCodeInput.setStyles({"border":"1px solid #ff0000"});
                    flag = false;
                }

                if(flag){
                    var data = {}
                    if(this.isEdited) data.id = this.data.id;
                    debugger
                    data.configModule = this.templateModuleInput.get("value").trim();
                    data.configType = this.templateConfigTypeInput.get("value").trim();
                    data.configName = this.templateConfigNameInput.get("value").trim();
                    data.configCode = this.templateConfigCodeInput.get("value").trim();
                    data.configValue = this.templateConfigValueInput.get("value").trim();
                    data.valueType = this.templateValueTypeInput.get("value").trim();
                    data.selectContent = this.templateSelectContentInput.get("value").trim();
                    data.isMultiple = this.templateIsMultipleInput.get("value").trim();
                    data.notEmpty = this.templateNotEmptyInput.get("value").trim();
                    data.orderNumber = this.templateOrderNumberInput.get("value").trim();
                    data.description = this.templateDesInput.get("value").trim();
                    if(data.isMultiple=="true"){
                        data.isMultiple = true;
                    }
                    if(data.notEmpty=="true"){
                        data.notEmpty = true;
                    }
                   if(this.isEdited){
                        _self.actions.updateConfig(data.id ,data,function(json){
                            debugger
                            _self.close(json);
                        })
                    }else{
                        _self.actions.saveConfig(data,function(json){
                            debugger
                            _self.close(json);
                        })
                    }

                }
            }.bind(this)
        })
        debugger
        if(this.isEdited){
            this.getTemplate(this.data.id,function(json){
                debugger
                this.templateModuleInput.set("value",json.configModule);
                this.templateConfigTypeInput.set("value",json.configType);
                this.templateConfigNameInput.set("value",json.configName);
                this.templateConfigCodeInput.set("value",json.configCode);
                this.templateConfigValueInput.set("value",json.configValue);
                this.templateValueTypeInput.set("value",json.valueType);
                this.templateSelectContentInput.set("value",json.selectContent);
                this.templateIsMultipleInput.set("value",json.isMultiple);
                this.templateNotEmptyInput.set("value",json.notEmpty);
                this.templateOrderNumberInput.set("value",json.orderNumber);
                this.templateDesInput.set("value",json.description);
            }.bind(this))
        }

    },
    getTemplate:function(id,callback){
        this.actions.getConfigById(id,function(json){
            callback(json.data)
        }.bind(this));
    }

});

MWF.xApplication.CRM.Config.SelectType = new Class({
    Extends: MWF.xApplication.CRM.Common.ToolTips,
    options : {
        // displayDelay : 300,
        hasArrow:false,
        event:"click"
    },
    _loadCustom : function( callback ){
        var _self = this;
        this.css = this.options.css;
        this.lp = this.options.lp;
        //this.data
        //this.contentNode
        var container = {
            "cursor":"pointer",
            "height":"40px",
            "width":"100%"
        };
        var text={
            "height":"25px","line-height":"25px","float":"left","width":"100%",
            "margin-left":"6px","margin-top":"8px",
            "font-size":"13px","color":"#666666","border-radius":"2px"
        };
        var icon = {
            "float":"right","width":"24px","height":"24px",
            "margin-top":"6px","margin-right":"8px",
            "background":"url(../x_component_TeamWork/$Task/default/icon/icon_dagou.png) no-repeat center"
        };

        var dataString = this.data.data;
        if(dataString.indexOf(":")>0){
            var dataList = dataString.split(":")[1];
            var dataArr = dataList.split("|");
            debugger
            dataArr.each(function(d){
                var allContainer = new Element("div",{styles:container}).inject(_self.contentNode);
                var allText = new Element("div",{styles:text,text:d}).inject(allContainer);
                allText.setStyles({"color":"#999999","border":"0px solid #999999"});
                allContainer.addEvents({
                    click:function(){
                        var data = {"value":d};
                        _self.close(data)
                        debugger
                       // _self.target.set("text",d)
                    }.bind(this),
                    mouseover:function(){this.setStyles({"background-color":"#f2f5f7"})},
                    mouseout:function(){this.setStyles({"background-color":""})}
                });
            });
        }



       /* var allContainer = new Element("div",{styles:container}).inject(this.contentNode);
        var allText = new Element("div",{styles:text,text:this.lp.dynamicAll}).inject(allContainer);
        allText.setStyles({"color":"#999999","border":"0px solid #999999"});

        allContainer.addEvents({
            click:function(){
                var data = {"value":"all"};
                this.close(data)
            }.bind(this),
            mouseover:function(){this.setStyles({"background-color":"#f2f5f7"})},
            mouseout:function(){this.setStyles({"background-color":""})}
        });

        var attachmentContainer = new Element("div",{styles:container}).inject(this.contentNode);
        var attachmentText = new Element("div",{styles:text,text:this.lp.dynamicAttachment}).inject(attachmentContainer);
        attachmentText.setStyles({"color":"#999999","border":"0px solid #999999"});

        attachmentContainer.addEvents({
            click:function(){
                var data = {"value":"attachment"};
                this.close(data)
            }.bind(this),
            mouseover:function(){this.setStyles({"background-color":"#f2f5f7"})},
            mouseout:function(){this.setStyles({"background-color":""})}
        });

        var chatContainer = new Element("div",{styles:container}).inject(this.contentNode);
        var chatText = new Element("div",{styles:text,text:this.lp.dynamicChat}).inject(chatContainer);
        chatText.setStyles({"color":"#999999","border":"0px solid #999999"});

        chatContainer.addEvents({
            click:function(){
                var data = {"value":"chat"};
                this.close(data)
            }.bind(this),
            mouseover:function(){this.setStyles({"background-color":"#f2f5f7"})},
            mouseout:function(){this.setStyles({"background-color":""})}
        });*/

        if(callback)callback();
    }

});
