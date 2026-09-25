o2.xApplication.CloudDocument = o2.xApplication.CloudDocument || {};
o2.xApplication.CloudDocument.Service = o2.xApplication.CloudDocument.Service || {};
o2.xApplication.CloudDocument.Service = new Class({
    Implements: [Options, Events],
    options: {
    },
    initialize:function(options){
        this.action = o2.Actions.load("x_program_center");
    },
    execute:function(fun,data,callback){
        var json = {
            "fun" : fun,
            "data" : data
        };
        callback = o2.typeOf(data)==="function" ? data : callback;

        this.action.InvokeAction.execute("cloudDocumentSrv",json,function( json ){
            if(callback){
                callback(json.data);
            }
        }.bind(this),function(json){
            //debugger
            alert("error");
        }.bind(this),false);
    },
    do:function(srv,fun,data,callback){
        var json = {
            "fun" : fun,
            "data" : data
        };
        callback = o2.typeOf(data)==="function" ? data : callback;

        this.action.InvokeAction.execute(srv,json,function( json ){
            if(callback){
                callback(json.data);
            }
        }.bind(this),function(json){
            //debugger
            alert("error");
        }.bind(this),false);
    },
});
o2.xApplication.CloudDocument.Util = o2.xApplication.CloudDocument.Util || {};
o2.xApplication.CloudDocument.Util = new Class({
    getAvatar:function(person){
        var portalHost = o2.Actions.getHost( "x_organization_assemble_personal" );
        return portalHost + "/x_organization_assemble_personal/jaxrs/icon/" + person;
    },
    loadHtml : function (path,data,callback){
        o2.loadHtml(path, function(loaded){
            var html = loaded[0].data;
            html = html.bindJson(data);
            var node = new Element("div",{"html":html});
            if(callback) callback(node);
        });
    },
    pagination : function (page,pageSize,dataList){
        //前端分页
        var total = dataList.length;
        var begin,end;
        if(total < pageSize) {
            end = total;
        }else{
            end = page * pageSize > total ? total:page * pageSize ;
        }
        begin = (page -1) * pageSize;

        var newDataList = [];
        for(var i = begin ; i < end ; i++){
            newDataList.push(dataList[i])
        }
        return newDataList;
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
    getAclName : function(acl){
        //1.可查看、创建和修改文档
        //2.只读
        //3.拒绝访问
        //4.审阅
        //5.Form Filling
        //6.评论
        var aclAliasArr = [0,1,2];
        var aclNameArr = ["创建者","管理员","访客"];
        var aclName ;
        for(var i = 0 ; i < aclAliasArr.length ; i ++){
            if(aclAliasArr[i]===acl){
                aclName = aclNameArr[i];
            }
        }
        return aclName;
    },
    timestampFormat : function(timestamp){
        function zeroize( num ) {
            return (String(num).length == 1 ? '0' : '') + num;
        }

        var curTimestamp = parseInt(new Date().getTime() / 1000); //当前时间戳
        var timestampDiff = curTimestamp - timestamp; // 参数时间戳与当前时间戳相差秒数

        var curDate = new Date( curTimestamp * 1000 ); // 当前时间日期对象
        var tmDate = new Date( timestamp * 1000 );  // 参数时间戳转换成的日期对象

        var Y = tmDate.getFullYear(), m = tmDate.getMonth() + 1, d = tmDate.getDate();
        var H = tmDate.getHours(), i = tmDate.getMinutes(), s = tmDate.getSeconds();

        if ( timestampDiff < 60 ) { // 一分钟以内
            return "刚刚";
        } else if( timestampDiff < 3600 ) { // 一小时前之内
            return Math.floor( timestampDiff / 60 ) + "分钟前";
        } else if ( curDate.getFullYear() == Y && curDate.getMonth()+1 == m && curDate.getDate() == d ) {
            return '今天' + zeroize(H) + ':' + zeroize(i);
        } else {
            var newDate = new Date( (curTimestamp - 86400) * 1000 ); // 参数中的时间戳加一天转换成的日期对象
            if ( newDate.getFullYear() == Y && newDate.getMonth()+1 == m && newDate.getDate() == d ) {
                return '昨天' + zeroize(H) + ':' + zeroize(i);
            } else if ( curDate.getFullYear() == Y ) {
                return  zeroize(m) + '月' + zeroize(d) + '日 ' + zeroize(H) + ':' + zeroize(i);
            } else {
                //return  Y + '年' + zeroize(m) + '月' + zeroize(d) + '日 ' + zeroize(H) + ':' + zeroize(i);
                return  Y + '年' + zeroize(m) + '月' + zeroize(d) + '日';
            }
        }
    },
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
});