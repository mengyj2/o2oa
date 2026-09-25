/********************
 this.entityManager; //实体管理器
 this.applications; //访问系统内服务
 this.requestText//请求正文
 this.request//请求
 this.currentPerson//当前用户
 this.response//响应对象。通过this.response.setBody(data)设置响应内容
 this.organization; //组织访问
 this.org; //组织快速访问方法
 this.service; ///webSerivces客户端
 ********************/

var host = request.getScheme() + "://" + request.getServerName();

var _self = this;
Util = new Class({
    Implements: [Options, Events],
    options: {
    },
    initialize: function (options) {
    },
    getPerson : function(person){

        print("getPerson=================")
        var personObj ;
        _self.Actions.load("x_organization_assemble_control").PersonAction.get(person,function( json ){
            personObj = json.data;
        }.bind(this));
        return personObj;

    },
    getApp:function(app){
        var resp;
        resp = applications.getQuery("x_program_center", "center/applications" ,"{}");
        var appJson = JSON.parse(resp.toString()).data;
        return appJson[app];
    },
    merge:function(obj1,obj2){
        for( var key in obj2 ){
            obj1[key] = obj2[key];
        }
        return obj1;
    },
    query:function(table,json){
        print("===========sql============" + JSON.stringify(json));
        var resp = applications.postQuery("x_query_assemble_designer", "table/" + table + "/execute",JSON.stringify(json));
        return JSON.parse(resp.toString()).data;
    },
    delete:function(table,id){
        var resp;
        resp = applications.deleteQuery("x_query_assemble_designer", "table/" + table + "/row/" + id,JSON.stringify(data));
        return JSON.parse(resp.toString()).data;
    },
    save : function(table,data){

        print("tablexxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        print(JSON.stringify(data))
        var resp;
        if(data.id){
            print("xxxxxx===============修改")
            //delete data.updateTime
            print(JSON.stringify(data))
            print("888888888888:" + "table/" + table + "/row/" + data.id)
            resp = applications.putQuery("x_query_assemble_designer", "table/" + table + "/row/" + data.id,JSON.stringify(data));
        }else{
            print("xxxxxx===============新增111111111111111111" + "table:" + table)
            resp = applications.postQuery("x_query_assemble_designer", "table/" + table + "/row",JSON.stringify(data));
            data.id = JSON.parse(resp.toString()).data.valueList[0];
        }
        return data;
    },
    fixedQueryField : function(returnField,dataList){
        var newDataList = [];
        for(var i = 0 ; i < dataList.length ; i ++){
            var d = {};
            var dd = dataList[i];
            for(var j = 0 ; j < returnField.length ; j++){
                d[returnField[j]] = dd[j];
            }
            newDataList.push(d);
        }
        return newDataList;
    }
});
var requestJson = JSON.parse(this.requestText);
var fun = requestJson.fun;
var data = requestJson.data;
var returnData = {
    "type" : "success",
    "message" : "",
};
var person = this.currentPerson.distinguishedName;
person = person.split("@").length>1 ? person.split("@")[1] : person;
var personName = this.currentPerson.name;
print(this.currentPerson)


print("fun:" + fun)

data.person = person;
data.personName = personName;
print("data:" + JSON.stringify(data));


var util = new Util();

CloudDocument = {};
CloudDocument.Document = new Class({
    options: {
    },
    initialize: function (options) {
        this.table = "document";
        this.documentAcl = new CloudDocument.DocumentAcl();
    },
    extendQuery : function(newDataList){
        if(newDataList.length>0){
            var inArr = [];
            newDataList.each(function(d){
                inArr.push("\"" + d.id + "\"")
            });
            json = {
                "type":"select",
                "data":"select o from document_tag o where o.documentId in (" + inArr.join(",") + ")"
            };
            var tagList = util.query("document_tag",json);

            newDataList.each(function(d){
                d.tagList = [];
                tagList.each(function (t){
                    if(d.id===t.documentId){
                        d.tagList.push(t.name);
                    }
                })
            });
            //fav
            json = {
                "type":"select",
                "data":"select o from document_fav o where o.person = '" + person + "' and  o.documentId in (" + inArr.join(",") + ")"
            };
            print("=======================")
            print(JSON.stringify(json))
            var favList = util.query("document_fav",json);
            newDataList.each(function(d){
                d.fav = false;
                favList.each(function (t){
                    if(d.id===t.documentId){
                        d.fav = true;
                    }
                })
            });
        }
        return newDataList;
    },
    queryDocumentByPage : function(page,pageSize,query,order,latest){

        var table = "document o,document_acl o2 ,document_tag o3,document_fav o4,document_latest o5";
        var firstResult = page === 1?0:(page-1)*pageSize;
        var searchArr = [];
        searchArr.push("1>0");

        var field = this.getField(latest);
        var returnField = field.returnField;

        var fieldArr = field.fieldArr;
        var newDataList = [];

        if(query){
            for(var i = 0 ; i < query.length ; i ++){
                searchArr.push(query[i]);
            }
        }
        if(!order){
            order = "o.updateTime desc";
        }
        var json = {
            "type":"select",
            "data":"select " + fieldArr.join() + " from " + table + " where " + searchArr.join(" and ") + " order by " + order,
            "maxResults":pageSize,
            "firstResult":firstResult
        };

        print(JSON.stringify(json))
        var countJson = {
            "type":"select",
            "data":"select count(o) from " + table + " where " + searchArr.join(" and "),
            "maxResults":pageSize,
            "firstResult":firstResult
        };
        var dataList = util.query("document",json);

        print("dataList:" + JSON.stringify(dataList))

        newDataList = util.fixedQueryField(returnField,dataList);
        newDataList = this.extendQuery(newDataList);
        var total = util.query("document",countJson);
        return {
            "dataList" : newDataList,
            "total" : total[0]
        }
    },
    getField : function(latest){
        var returnField = [];
        var fieldArr = [];
        returnField.push("id");
        returnField.push("person");
        returnField.push("personName");
        returnField.push("documentId");
        returnField.push("fileName");
        returnField.push("fileSize");
        returnField.push("folderId");
        returnField.push("fileType");
        returnField.push("version");
        returnField.push("comment");
        returnField.push("status");
        returnField.push("updateTime");
        returnField.push("createTime");
        returnField.push("updater");
        returnField.push("online");

        for(var i = 0 ; i < returnField.length ; i ++){
            if(latest && returnField[i]==="updateTime"){
                fieldArr.push("o5." + returnField[i]);
            }else{
                fieldArr.push("o." + returnField[i]);
            }

        }

        return {
            returnField : returnField,
            fieldArr : fieldArr
        };
    },
    checkReader : function (documentId,person){

        var documentData = this.get(documentId);
        if(documentData.id){
            var aclData = this.documentAcl.getPersonAcl(documentId,person);
            documentData.aclData = aclData;
            if(!aclData.id){
                documentData = {};
            }
        }
        return documentData;
    },
    checkOwner : function (documentId,person){

        var documentData = this.get(documentId);
        if(documentData.id){
            if(documentData.person !== person){
                documentData = {};
            }
            // var aclData = this.documentAcl.getPersonAcl(documentId,person);
            // documentData.aclData = aclData;
            // if(!aclData.id){
            //     documentData = {};
            // }else{
            //     if(aclData.acl !== 0){
            //         documentData = {};
            //     }
            // }
        }
        return documentData;
    },
    getNewFileName : function(folderId,fileName,fileType,person){
        this.fileName = fileName;
        this._checkFileName(folderId,fileName,fileType,person)
        return this.newFileName;
    },
    _checkFileName : function (folderId,fileName,fileType,person,index){
        if(!index) index = 0;
        index = index + 1;
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.person = '" + person + "' and o.fileType='" + fileType + "' and o.fileName='" + fileName + "' and o.folderId = '" + folderId + "'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            fileName = this.fileName  + "(" + index + ")"
            this._checkFileName(folderId,fileName,fileType,person,index);
        }else{
            this.newFileName = fileName;
        }
    },
    getFolderDocument : function (folderId,person){
        //获取文件夹下的所有文档
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.person = '" + person + "' and o.folderId = '" + folderId + "'"
        };
        return util.query(this.table,json);
    },
    save : function(data){
        return util.save(this.table,data);
    },
    getByDocumentId : function(id){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.documentId = '" + id + "'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    },
    get : function(id){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.id = '" + id + "'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    },
    delete : function(id){
        var json = {
            "type":"delete",
            "data":"delete from "+ this.table +" o where o.id = '" + id + "' "
        };
        util.query(this.table,json);
    },
    clear : function (documentId){
        var json = {
            "type":"delete",
            "data":"delete from "+ this.table +" o where o.documentId = '" + documentId + "' "
        };
        util.query(this.table,json);
    },
    update : function(id,setArr){
        var json = {
            "type":"update",
            "data":"update "+ this.table +" o  set "  + setArr.join() + "o.id = '" + id + "'"
        };
        util.query(this.table,json);
    }
});
CloudDocument.OnlyOffice = new Class({
    initialize: function (options) {
        this.onlyofficeSrv = "x_onlyoffice_assemble_control";
        this.resp = "";
    },
    getConfig : function(){
        this.resp = applications.getQuery( this.onlyofficeSrv, "onlyofficeconfig/get"  , "{}");
        return JSON.parse(this.resp.toString()).data;
    },
    removeHistory : function(documentId,verison){
        this.resp = applications.deleteQuery( this.onlyofficeSrv, "onlyoffice/delete/"+documentId+"/version/" + verison );
        print("xxxxxxxxsdfasdfasdff")
        print(this.resp)
    },
    removeDocument : function (documentId){
        this.resp = applications.deleteQuery( this.onlyofficeSrv, "onlyoffice/delete/" + documentId );
        print(this.resp);
    },
    renameDocument : function (documentId,fileName){
        print("documentId:" + documentId)
        print("fileName:" + fileName)
        var json = {
            "fileName" : fileName
        }
        this.resp = applications.postQuery( this.onlyofficeSrv, "onlyoffice/file/rename/" + documentId , JSON.stringify(json));

        print(this.resp)

        return JSON.parse(this.resp.toString()).data;
    },
    copyDocument : function (documentId,fileName){
        print("documentId:" + documentId)
        print("fileName:" + fileName)
        var json = {
            "fileName" : fileName
        }
        this.resp = applications.postQuery( this.onlyofficeSrv, "onlyoffice/copy/"+documentId , JSON.stringify(json));

        print(this.resp)

        return JSON.parse(this.resp.toString()).data;
    },
    getDocument : function(documentId){
        this.resp = applications.getQuery( this.onlyofficeSrv, "onlyoffice/"+documentId , "{}");
        return JSON.parse(this.resp.toString()).data;
    },
    getDocumentVersion : function(documentId,version){
        this.resp = applications.getQuery( this.onlyofficeSrv, "onlyoffice/file/"+documentId+"/"+version , "{}");
        return JSON.parse(this.resp.toString()).data;
    },
    createtoken : function(documentId,editor){
        var json = {
            type : editor.type,
            documentType : editor.documentType,
            document : editor.document,
            editorConfig : editor.editorConfig
        }
        this.resp = applications.postQuery( this.onlyofficeSrv, "onlyoffice/createtoken/"+documentId , JSON.stringify(json));
        return JSON.parse(this.resp.toString()).data.value;
    },
    getFileToken : function(documentId){
        this.resp = applications.getQuery( this.onlyofficeSrv, "onlyoffice/token/" + documentId , "{}");
        return JSON.parse(this.resp.toString()).data.fileToken;
    },
    createDocument : function(data){
        var json = {
            "fileName" : data.fileName + "." + data.fileType,
            "fileType" : data.fileType
        }
        this.resp = applications.postQuery( this.onlyofficeSrv, "onlyoffice/create" , JSON.stringify(json));
        var officeDocument = JSON.parse(this.resp.toString()).data;
        return officeDocument;
    }
});
CloudDocument.DocumentLog = new Class({
    Extends: CloudDocument.Document,
    initialize: function (options) {
        this.table = "document_log";
    },
    addLog : function(person,op,documentId,desc){
        var ip;
        if (request.getHeader("x-forwarded-for") == null) {
            ip =request.getRemoteAddr();
        }else{
            ip = request.getHeader("x-forwarded-for");
        }
        return this.save({
            "person" : person,
            "op" : op,
            "ip":ip,
            "documentId": documentId,
            "desc" : !desc?"":desc
        });
    },
});
CloudDocument.DocumentLatest = new Class({
    Extends: CloudDocument.Document,
    initialize: function (options) {
        this.table = "document_latest";
    },
    getPersonLatest : function (documentId,person) {
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.documentId = '" + documentId + "' and o.person='"+ person +"'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    }
});
CloudDocument.DocumentOnline = new Class({
    Extends: CloudDocument.Document,
    initialize: function (options) {
        this.table = "document_online";
    },
    getDocumentOnline : function (documentId) {
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.documentId = '" + documentId + "'"
        };
        return util.query(this.table,json);
    },
    getPersonOnline : function (documentId,person) {
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.documentId = '" + documentId + "' and o.person='"+ person +"'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    }
});
CloudDocument.DocumentAcl = new Class({
    Extends: CloudDocument.Document,
    initialize: function (options) {
        this.table = "document_acl";
    },
    getDocumentAcl : function(documentId){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.documentId = '" + documentId  +"'"
        };
        return util.query(this.table,json);
    },
    getPersonAcl : function (documentId,person){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.documentId = '" + documentId + "' and o.person='"+ person +"'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    }
});
CloudDocument.DocumentFav = new Class({
    Extends: CloudDocument.Document,
    initialize: function (options) {
        this.table = "document_fav";
    },
    getPersonFav : function (documentId,person){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.documentId = '" + documentId + "' and o.person='"+ person +"'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    }
});
CloudDocument.DocumentFolder = new Class({
    Extends: CloudDocument.Document,
    initialize: function (options) {
        this.table = "document_folder";
    },
    getAllFolder : function (id){
        //获取文件夹+文件夹下的所有文件夹
        this.allFolder = [];
        if(id!=="-1"){
            this.parseFolder(id);
            this.allFolder.push(this.get(id));
        }
        return this.allFolder;
    },
    parseFolder : function (id){
        var folderList = this.getFolders(id);
        for(var i = 0 ; i < folderList.length ; i++){
            var folder = folderList[i];
            var l = this.getFolders(folder.id);
            print("folder.name:" + folder.name);
            print("l:" + l.length);
            if(l.length>0){
                this.parseFolder(folder.id);
            }
            this.allFolder.push(folder);
        }
    },
    getFolderList : function (id,person){
        //获取文件夹下的文件夹
        var queryArr = [];
        queryArr.push("o.parentId='" + id + "'");
        queryArr.push("o.person = '" + person + "'");
        queryArr.push("(o.status <> 'remove' or o.status is null)");
        var json = {
            "type":"select",
            "data":"select o from "+ this.table + " o where " + queryArr.join(" and "),
        };
        var folderList  = util.query(this.table,json);
        if(folderList.length>0){
            var inArr = [];
            folderList.each(function(d){
                inArr.push("\"" + d.id + "\"")
            });
            json = {
                "type":"select",
                "data":"select o from document_tag o where o.documentId in (" + inArr.join(",") + ")"
            };
            var tagList = util.query("document_tag",json);
            folderList.each(function(d){
                d.tagList = [];
                tagList.each(function (t){
                    if(d.id===t.documentId){
                        d.tagList.push(t.name);
                    }
                })
            });
        }
        return folderList;
    },
    getFolders : function (id){
        //获取文件夹下的文件夹
        var queryArr = [];
        queryArr.push("o.parentId='" + id + "'");
        var json = {
            "type":"select",
            "data":"select o from "+ this.table + " o where " + queryArr.join(" and "),
        };
        return util.query(this.table,json);
    },
    getPersonFolder : function (folderId,person){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.id = '" + folderId + "' and o.person='" + person + "'"
        };
        if(folderId === "-1"){
            return {
                id : "-1",
                name : "根目录"
            }
        }
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    },
    getNewFolderName : function(person,parentId,folderName){
        print("getNewFolderName")
        this.folderName = folderName;
        this._checkFolderName(person,parentId,folderName)
        return this.newFolderName;
    },
    _checkFolderName : function (person,parentId,folderName,index){
        if(!index) index = 0;
        index = index + 1;
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.person = '" + person + "' and  o.parentId='" + parentId + "' and o.name='" + folderName + "'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            folderName = this.folderName  + "(" + index + ")"
            this._checkFolderName(person,parentId,folderName,index);
        }else{
            this.newFolderName = folderName;
        }
    },
});
CloudDocument.DocumentVersion = new Class({
    Extends: CloudDocument.Document,
    initialize: function (options) {
        this.table = "document_version";
    },
    getDocumentVersion : function (documentId,version){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.documentId = '" + documentId + "' and o.version="+ version
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    },
    getDocumentVersionList : function (documentId) {
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.documentId = '" + documentId + "'"
        };
        return util.query(this.table,json);
    }
});
CloudDocument.DocumentTag = new Class({
    Extends: CloudDocument.Document,
    initialize: function (options) {
        this.table = "document_tag";
    },
    getDocumentTag : function (documentId,tag){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.documentId = '" + documentId + "' and o.name='"+ tag + "'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    }
});
CloudDocument.DocumentTeam = new Class({
    Extends: CloudDocument.Document,
    initialize: function (options) {
        this.table = "document_team";
    },
    getPersonTeamById : function (id,person){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.person = '" + person + "' and o.id='"+ id + "'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    },
    getPersonTeam : function (name,person){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.person = '" + person + "' and o.name='"+ name + "'"
        };
        var dataList = util.query(this.table,json);
        if(dataList.length>0){
            return dataList[0];
        }else{
            return {};
        }
    },
    getPersonTeamList : function (person){
        var json = {
            "type":"select",
            "data":"select o from "+ this.table +" o where o.person = '" + person + "'"
        };
        return util.query(this.table,json);
    }
});
CloudDocument.Main = new Class({
    initialize: function (fun,data) {
        this.document = new CloudDocument.Document();
        this.documentLog = new CloudDocument.DocumentLog();
        this.documentLatest = new CloudDocument.DocumentLatest();
        this.documentOnline = new CloudDocument.DocumentOnline();
        this.documentAcl = new CloudDocument.DocumentAcl();
        this.documentFav = new CloudDocument.DocumentFav();
        this.documentFolder = new CloudDocument.DocumentFolder();
        this.documentVersion = new CloudDocument.DocumentVersion();
        this.documentTag = new CloudDocument.DocumentTag();
        this.documentTeam = new CloudDocument.DocumentTeam();
        this.onlyOffice = new CloudDocument.OnlyOffice();
        this.data = data;
        this.person = this.data.person;
        this.personName = this.data.personName;

        this[fun]();
    },
    openDocument : function(){
        var documentId = this.data.documentId;
        var person = this.data.userId;

        print("documentId" + documentId)
        print("person:" + person)
        this._addDocumentOnline(documentId,person);
    },
    closeDocument : function(){
        var documentId = this.data.documentId;
        var person = this.data.userId;


        print("documentId" + documentId)
        print("person:" + person)
        this._removeDocumentOnline(documentId,person);
    },
    getDocumentToken : function(){
        var documentId = this.data.documentId;
        var documentData = this.document.checkReader(documentId,this.person);
        if(documentData.id ){
            var token = this.onlyOffice.getFileToken(documentData.documentId);
            //log
            this.documentLog.addLog(this.person,"下载文档",documentData.id);
            returnData.data = {
                fileToken : token
            }
        }
    },
    updateDocument : function(){
        //回调更新文档

        var documentId = this.data.documentId;
        print("回调更新文档==================================begin：" + documentId)
        var officeDocument = this.onlyOffice.getDocument(documentId);
        var documentData = this.document.getByDocumentId(documentId);
        documentData.fileSize = officeDocument.fileSize;

        var fileHistory = JSON.parse(officeDocument.FileHistory[0]);
        var versionList = fileHistory.history;

        documentData.version = fileHistory.currentVersion;

        var currentVersion = versionList[fileHistory.currentVersion];

        documentData.updater = currentVersion.user.name;
        this.document.save(documentData);

        versionList.each(function(version){

            var versionData = this.documentVersion.getDocumentVersion(documentData.id,version.version);

            if(!versionData.id){
                versionData.person = version.user.name;
                versionData.version = version.version;
                versionData.documentId = documentData.id;
                versionData.documentKey = version.key;
                versionData.changeTime = version.created;
                versionData.changes = JSON.stringify(version.changes);
                this.documentVersion.save(versionData);
            }

        }.bind(this));
        print("回调更新文档==================================end" )
    },
    createDocument : function (){
        //未完成，检查folderId 有效性
        this.data.fileName = this.document.getNewFileName(this.data.folderId,this.data.fileName,this.data.fileType,this.person);

        if(!this.data.documentId){
            var officeDocument = this.onlyOffice.createDocument(this.data);
            this.data.documentId = officeDocument.id;
            this.data.fileSize = officeDocument.fileSize;
        }

        documentData = this.document.save(this.data);
        var aclData = {
            "person" : this.data.person,
            "personName" : this.data.personName,
            "acl" : 0,
            "documentId" : documentData.id
        }
        this.documentAcl.save(aclData);
        this.documentLog.addLog(this.data.person,"创建文档",documentData.id);
        returnData.data = documentData;
    },
    moveDocument : function (){
        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);

        var newFolderId = this.data.newFolderId;
        var folderData = this.documentFolder.getPersonFolder(newFolderId,this.person);


        if(documentData.id && folderData.id){
            if(documentData.folderId !== newFolderId){
                var oldFolderId = documentData.folderId;
                documentData.folderId = newFolderId;
                this.document.save(documentData);
                this.documentLog.addLog(this.person,"移动文件夹",documentId,"原文件夹："  + oldFolderId + "，新文件夹:" + newFolderId);
            }
        }
        return this.returnData;
    },
    copyDocument : function (){

        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);

        var folderId = this.data.newFolderId;
        var folderData = this.documentFolder.getPersonFolder(folderId,this.person);

        if(documentData.id && folderData.id){
            documentData.folderId = this.data.newFolderId;
            delete documentData.id;

            documentData.fileName = this.document.getNewFileName(folderId,documentData.fileName,documentData.fileType,this.person);
            var officeDocument = this.onlyOffice.copyDocument(documentData.documentId,documentData.fileName+"." + documentData.fileType);
            documentData.documentId = officeDocument.id;

            documentData = this.document.save(documentData);
            var aclData = {
                "person" : this.person,
                "personName" : this.personName,
                "acl" : 0,
                "documentId" : documentData.id
            }
            this.documentAcl.save(aclData);
            this.documentLog.addLog(this.person,"复制文档","复制到：" + folderData.name);
            returnData.data = documentData;
        }
        return this.returnData;
    },
    addDocumentOnline : function(){

        // var documentId = this.data.documentId;
        // var documentData = this.document.checkReader(documentId,this.person);
        // if(documentData.id){
        //     var onlineData = this.documentOnline.getPersonOnline(documentId,this.person);
        //     if(onlineData.id){
        //         this.documentOnline.delete(onlineData.id);
        //     }
        //     onlineData = {
        //         person : this.person,
        //         personName : personName,
        //         documentId : documentId,
        //     }
        //     this.documentOnline.save(onlineData);


        // }
    },
    _addDocumentOnline : function(documentId,person){

        var personObj = util.getPerson(person);
        var documentData = this.document.getByDocumentId(documentId);
        if(documentData.id){
            var onlineData = this.documentOnline.getPersonOnline(documentData.id,person);
            if(onlineData.id){
                this.documentOnline.delete(onlineData.id);
            }
            onlineData = {
                person : person,
                personName : personObj.name,
                documentId : documentData.id,
            }
            this.documentOnline.save(onlineData);
            this.documentLog.addLog(person,"查看文档",documentData.id);
        }
    },
    _removeDocumentOnline : function(documentId,person){
        print("_removeDocumentOnline")
        var documentData = this.document.getByDocumentId(documentId);
        if(documentData.id){
            var onlineData = this.documentOnline.getPersonOnline(documentData.id,person);
            if(onlineData.id){
                this.documentOnline.delete(onlineData.id);
            }
        }
    },
    getDocumentOnline : function(){
        var documentId = this.data.documentId;
        var documentData = this.document.checkReader(documentId,this.person);
        if(documentData.id){
            returnData.data = this.documentOnline.getDocumentOnline(documentId);
        }
    },
    setDocumentOnline : function (){
        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){

            documentData.online = this.data.online;
            documentData = this.document.save(documentData);

            this.documentLog.addLog(this.person,"设置在线人数",documentData.id,"设置同时在线人数为：" + documentData.online);

            returnData.data = documentData;
        }
    },
    renameDocument : function (){
        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            var oldName = documentData.fileName;
            documentData.fileName = this.data.name;
            documentData.fileName = this.document.getNewFileName(documentData.folderId,documentData.fileName,documentData.fileType,this.person);
            documentData = this.document.save(documentData);

            this.onlyOffice.renameDocument(documentData.documentId,documentData.fileName+"." + documentData.fileType);

            var logDesc = "原文件名：" + oldName + ".修改后的文件名：" + documentData.fileName
            this.documentLog.addLog(this.person,"文档重命名",documentData.id,logDesc);

            returnData.data = documentData;
        }
    },
    removeDocument : function (){
        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            if(data.soft){
                documentData.status = "remove";
                this.document.save(documentData);
                this.documentLog.addLog(this.person,"软删除文件",documentId);
            }else{
                this._removeDocument(documentId);
            }
        }
    },
    removeHistory : function (){
        var documentId = this.data.documentId;
        var version = this.data.version;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            this.onlyOffice.removeHistory(documentData.documentId,version);
            var versionData = this.documentVersion.getDocumentVersion(documentId,version);
            if(versionData.id){
                this.documentVersion.delete(versionData.id)
            }
            this.documentLog.addLog(this.person,"删除历史版本",documentId,"删除版本:" + this.data.version);
        }
    },
    _removeDocument : function (documentId){
        this.onlyOffice.removeDocument(documentId);
        this.document.delete(documentId);

        this.documentAcl.clear(documentId);
        this.documentFav.clear(documentId);
        this.documentLatest.clear(documentId);
        this.documentTag.clear(documentId);
        this.documentOnline.clear(documentId);
        this.documentVersion.clear(documentId);

        this.documentLog.addLog(this.person,"删除文档",documentId);
    },
    resumeFolder : function (){
        var folderId = this.data.folderId;
        var folderData = this.documentFolder.getPersonFolder(folderId,this.person);
        if(folderData.id){
            var folderList = this.documentFolder.getAllFolder(folderId);
            folderList.each(function (folder){
                var documentList = this.document.getFolderDocument(folder.id,this.person);
                documentList.each(function (d){
                    d.status = '';
                    this.document.save(d);
                }.bind(this));

                folder.status = '';
                this.documentFolder.save(folder);
            }.bind(this));
        }
    },
    resumeDocument : function (){
        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            documentData.status = "";
            this.document.save(documentData);
            this.documentLog.addLog(this.person,"还原文件",documentData.documentId);
        }
    },
    addLatest : function (){
        var documentId = this.data.documentId;
        var documentData = this.document.checkReader(documentId,this.person);
        if(documentData.id){
            var latestData = this.documentLatest.getPersonLatest(documentId,this.person);
            if(latestData.id){
                this.documentLatest.delete(latestData.id);
            }
            this.documentLatest.save(this.data);
        }
    },
    addFav : function (){
        var documentId = this.data.documentId;
        var documentData = this.document.checkReader(documentId,this.person);
        if(documentData.id){
            var favData = this.documentFav.getPersonFav(documentId,this.person);
            if(!favData.id){
                this.documentFav.save(this.data);
                this.documentLog.addLog(this.person,"添加收藏",documentId);
            }
        }
    },
    deleteFav : function (){
        var documentId = this.data.documentId;
        var documentData = this.document.checkReader(documentId,this.person);
        if(documentData.id){
            var favData = this.documentFav.getPersonFav(documentId,this.person);
            if(favData.id){
                this.documentFav.delete(favData.id);
                this.documentLog.addLog(this.person,"取消收藏",documentId);
            }
        }
    },
    getUserCapacity : function (){
        var json = {
            "type":"select",
            "data":"select sum(o.fileSize) from document o where o.person = '"+ data.person +"'"
        };
        returnData.data = {total:util.query("document",json)[0]};
    },
    getTeamCapacity : function (){
        var json = {
            "type":"select",
            "data":"select sum(o.fileSize) from document o where o.teamId = '"+ data.teamId +"'"
        };
        returnData.data = {total:util.query("document",json)[0]};
    },
    createFolder : function (){
        this.data.name = this.documentFolder.getNewFolderName(this.person,this.data.parentId,this.data.name);
        var folderData = this.documentFolder.save(data);
        this.documentLog.addLog(this.person,"创建文件夹",folderData.id,this.data.name);
        returnData.data = folderData;
    },
    renameFolder : function (){
        var folderId = this.data.folderId;
        var folderData = this.documentFolder.getPersonFolder(folderId,this.person);

        if(folderData.id){
            var oldName = folderData.name;
            folderData.name = this.data.name;
            folderData.name = this.documentFolder.getNewFolderName(this.person,folderData.id,folderData.name);
            folderData = this.documentFolder.save(folderData);
            var logDesc = "原文件夹名：" + oldName + ".修改后的文件夹：" + folderData.name
            this.documentLog.addLog(this.person,"重命名文件夹",folderData.id,logDesc);

            returnData.data = folderData;
        }
    },
    addAcl : function(){

        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            this.data.dataList.each(function(aclData){
                aclData.documentId = documentId;

                var oldAclData = this.documentAcl.getPersonAcl(documentId,aclData.person);
                if(!oldAclData.id){
                    this.documentAcl.save(aclData);
                    this.documentLog.addLog(this.person,"增加权限",data.documentId,"增加："  + aclData.person);
                }

            }.bind(this))
        }
    },
    updateAcl : function(){

        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            var aclData = this.documentAcl.getPersonAcl(documentId,this.data.aclPerson);
            if(aclData.id) {
                var oldAcl = aclData.acl;
                aclData.acl = this.data.acl;
                this.documentAcl.save(aclData);
                this.documentLog.addLog(this.person, "更新权限", documentId ,oldAcl + "更新为：" + this.data.acl);
            }
        }
    },
    removeAcl : function(){

        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            var aclData = this.documentAcl.getPersonAcl(documentId,this.data.aclPerson);
            if(aclData.id) {

                this.documentAcl.delete(aclData.id);
                this.documentLog.addLog(this.person, "删除权限", documentId ,this.data.aclPerson);
            }
        }
    },
    updateDocumentVersion : function(){
        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            var version = this.data.version;
            var versionData = this.documentVersion.getDocumentVersion(documentId,version);
            if(versionData.id){
                versionData.comment = this.data.comment;
                this.documentVersion.save(versionData);
                this.documentLog.addLog(this.person, "添加备注", documentId ,this.data.comment);
            }
        }
    },
    getDocumentVersion : function(){
        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            var version = this.data.version;
            returnData.data = this.documentVersion.getDocumentVersion(documentId,version);
        }
    },
    getDocumentAcl : function(){
        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            var aclList = this.documentAcl.getDocumentAcl(documentId);
            var newAclList = [];
            aclList.each(function(acl){
                newAclList.push({
                    "person" : acl.person,
                    "personName" : acl.personName,
                    "acl" : acl.acl
                })
            })
            returnData.data = newAclList;
        }
    },
    getDocumentVersionList : function(){
        var documentId = this.data.documentId;
        var documentData = this.document.checkOwner(documentId,this.person);
        if(documentData.id){
            var versionList = this.documentVersion.getDocumentVersionList(documentId);

            for(var i=0;i<versionList.length-1;i++){
                for(var j=i+1;j<versionList.length;j++){
                    if(versionList[i].version<versionList[j].version){
                        var temp=versionList[i];
                        versionList[i]=versionList[j];
                        versionList[j]=temp;
                    }
                }
            }

            returnData.data = versionList;
        }
    },
    getFolderList : function (){
        //获取文件夹的下级文件夹
        var folderId = this.data.folderId;
        //var folderData = this.documentFolder.getPersonFolder(folderId,this.person);
        //if(folderData.id){
        returnData.data = this.documentFolder.getFolderList(folderId,this.person);
        //}
    },
    getEditor : function(){

        var documentId = this.data.documentId;
        var documentData = this.document.checkReader(documentId,this.person);
        if(documentData.id){

            var onlineList = this.documentOnline.getDocumentOnline(documentId);
            documentData.curOnline = onlineList.length;

            var version = this.data.version;
            var mode = this.data.mode;
            if(!mode) mode = "edit";
            var officeDocument;

            if(!version){
                officeDocument = this.onlyOffice.getDocument(documentData.documentId);
            }else{
                officeDocument = this.onlyOffice.getDocumentVersion(documentData.documentId,version);
            }

            documentData.FileHistory = officeDocument.FileHistory;
            if(documentData.FileHistory[0]!==""){
                var history = JSON.parse(documentData.FileHistory[1]);
                for (var key in history) {
                    history[key].url = host + ":" + history[key].url.split(":")[2];
                    if(history[key].changesUrl){
                        history[key].changesUrl = host + ":" + history[key].changesUrl.split(":")[2];
                    }

                }
                documentData.FileHistory[1] = JSON.stringify(history);
            }

            var aclData = this.documentAcl.getPersonAcl(documentId,this.person);
            var acl = aclData.acl;

            if(mode === "edit"){
                if(acl > 1){
                    mode = "view";
                }
            }
            documentData.editor = {
                "type": "desktop",
                "documentType": officeDocument.fileModel.documentType,
                "document": {
                    "key" : officeDocument.fileModel.document.key,
                    "title": documentData.fileName,
                    "url": officeDocument.fileModel.document.url,
                    "fileType": documentData.fileType,
                    "permissions": {
                        "comment": true,
                        "download": true,
                        "edit": true,
                        "copy":true,
                        "fillForms": true,
                        "modifyFilter": true,
                        "modifyContentControl": true,
                        "review": true
                    }
                },
                "editorConfig": {
                    "mode": mode,
                    "callbackUrl": officeDocument.fileModel.editorConfig.callbackUrl,
                    "user": {
                        "id": this.person,
                        "name": personName
                    },
                    "lang": "zh",
                    "customization": {
                        "logo": {
                            "image": "http://doc.o2oa.net/x_component_CloudDocumentEditor/$Main/default/logo.png",
                            "imageEmbedded": "http://doc.o2oa.net/x_component_CloudDocumentEditor/$Main/default/logo.png",
                            "url": "http://o2oa.net"
                        },
                        "customer": {
                            "name": "O2OA",
                            "address": "杭州西湖区古翠路108号",
                            "mail": "admin@o2oa.net",
                            "www": "o2oa.net",
                            "info": "免费开源办公平台",
                            "logo": ""
                        },
                        "about": false,
                        "chat": false,
                        "comments": false,
                        "feedback": false,
                        "forcesave": false,
                        "goback": {
                            "url": "/x_desktop/document.html?app=CloudDocument&debugger"
                        }
                    }
                },
                "token": officeDocument.fileModel.token,
                "events": {}
            }

            var gobackUrl = documentData.editor.editorConfig.customization.goback.url;
            var documentUrl = documentData.editor.document.url;
            var callbackUrl = documentData.editor.editorConfig.callbackUrl;

            documentUrl = host + ":" + documentUrl.split(":")[2];
            callbackUrl = host + ":" + callbackUrl.split(":")[2];
            gobackUrl = host + gobackUrl;

            documentData.editor.editorConfig.customization.goback.url = gobackUrl;
            documentData.editor.document.url = documentUrl;
            documentData.editor.editorConfig.callbackUrl = callbackUrl;


            documentData.editor.token = this.onlyOffice.createtoken(documentId,documentData.editor);

            var onlyOfficeConfig = this.onlyOffice.getConfig();
            //print(JSON.stringify(onlyOfficeConfig))
            documentData.docserviceApi = onlyOfficeConfig.docserviceApi;
            returnData.data = documentData;
        }
    },
    addTag : function(){

        var documentId = this.data.documentId;
        var documentData = this.document.checkReader(documentId,this.person);
        if(documentData.id){
            var tag = this.data.tag;
            var tagData = this.documentTag.getDocumentTag(documentId,tag);

            if(!tagData.id){
                tagData.documentId = documentId;
                tagData.name = tag;
                this.documentTag.save(tagData);
                this.documentLog.addLog(this.person,"添加标签",documentId,tag);
            }
        }
    },
    removeTag : function(){
        var documentId = this.data.documentId;
        var documentData = this.document.checkReader(documentId,this.person);
        if(documentData.id){
            var tag = this.data.tag;
            var tagData = this.documentTag.getDocumentTag(documentId,tag);

            if(tagData.id){
                tagData.documentId = documentId;
                tagData.name = tag;
                this.documentTag.delete(tagData.id);
                this.documentLog.addLog(this.person,"删除标签",documentId,tag);
            }
        }
    },
    queryDocumentByPage : function(){

        var page = this.data.page;
        var pageSize = this.data.pageSize;
        if(!page) page = 1;
        if(!pageSize) pageSize = 100;

        var query  = [];
        if(this.data.folderId){
            query.push("o.folderId='" + data.folderId + "'");
        }
        if(this.data.isRemove){
            query.push("o.status = 'remove'");
        }else{
            query.push("(o.status <> 'remove' or o.status is null)");
        }
        if(this.data.key){
            query.push("o.fileName like '%" + this.data.key + "%'");
        }
        query.push("o.person = '" + this.person + "'");

        // query.push("o.id=o2.documentId");
        // query.push("o2.acl  < 5");
        // query.push("o2.person = '" + this.person + "'");
        returnData.data = this.document.queryDocumentByPage(page,pageSize,query);
    },
    queryShareToMeByPage : function(){
        var page = this.data.page;
        var pageSize = this.data.pageSize;
        if(!page) page = 1;
        if(!pageSize) pageSize = 100;

        var query  = [];
        query.push("o.id = o2.documentId");
        query.push("o2.acl > 0");
        query.push("(o.status <> 'remove' or o.status is null)");
        query.push("o2.person='" + this.person + "'");
        returnData.data = this.document.queryDocumentByPage(page,pageSize,query);
    },
    queryMyShareByPage : function(){
        var page = this.data.page;
        var pageSize = this.data.pageSize;
        if(!page) page = 1;
        if(!pageSize) pageSize = 100;

        var query  = [];
        query.push("exists(select o2 from document_acl o2 where o.id = o2.documentId and o2.acl > 0)");
        query.push("(o.status <> 'remove' or o.status is null)");
        query.push("o.person='" + person + "'");
        returnData.data = this.document.queryDocumentByPage(page,pageSize,query);
    },
    queryTagByPage : function(){

        var page = this.data.page;
        var pageSize = this.data.pageSize;
        if(!page) page = 1;
        if(!pageSize) pageSize = 100;

        var query  = [];
        query.push ("o2.person='" + this.person + "'");
        query.push("o.id = o2.documentId");
        query.push("o2.acl  < 5");
        query.push("o.id = o3.documentId");
        query.push("o3.name = '"+this.data.tag+"'");
        query.data = this.document.queryDocumentByPage(page,pageSize,query);
        returnData.data = this.document.queryDocumentByPage(page,pageSize,query);
    },
    queryFavByPage : function (){
        var page = this.data.page;
        var pageSize = this.data.pageSize;
        if(!page) page = 1;
        if(!pageSize) pageSize = 100;

        var query  = [];
        var query = ["o4.person='" + this.person + "'"];
        query.push("o.id = o4.documentId");
        query.push("(o.status <> 'remove' or o.status is null)");

        query.data = this.document.queryDocumentByPage(page,pageSize,query);
        returnData.data = this.document.queryDocumentByPage(page,pageSize,query);
    },
    queryLatestByPage : function (){
        var page = this.data.page;
        var pageSize = this.data.pageSize;
        if(!page) page = 1;
        if(!pageSize) pageSize = 100;

        var query  = [];
        var query = ["o5.person='" + this.person + "'"];
        query.push("o.id = o5.documentId");
        query.push("(o.status <> 'remove' or o.status is null)");

        returnData.data = this.document.queryDocumentByPage(page,pageSize,query,"o5.updateTime desc",true);
    },
    removeFolder : function (){
        var folderId = this.data.folderId;
        var folderData = this.documentFolder.getPersonFolder(folderId,this.person);
        if(folderData.id){
            var folderList = this.documentFolder.getAllFolder(folderId);
            if(this.data.soft){
                folderList.each(function (folder){
                    //获取文件夹下的所有文档
                    //然后软删除文档
                    var documentList = this.document.getFolderDocument(folder.id,this.person);
                    documentList.each(function (d){
                        d.status = 'remove';
                        this.document.save(d);
                    }.bind(this));

                    folder.status = 'remove';
                    this.documentFolder.save(folder);

                }.bind(this));

                this.documentLog.addLog(this.person,"软删除文件夹",folderData.id);
            }else {
                print("开始硬删除文件夹")

                folderList.each(function (folder){
                    //获取文件夹下的所有文档
                    //然后删除文档
                    var documentList = this.document.getFolderDocument(folder.id,this.person);
                    documentList.each(function (d){
                        this._removeDocument(d.id);
                    }.bind(this));

                    this.documentFolder.delete(folder.id);
                    this.documentLog.addLog(data.person,"删除文件夹",folder.id);
                }.bind(this));
            }
        }
    },
    getTeamList : function (){
        var teamList = this.documentTeam.getPersonTeamList(this.person);
        teamList.each(function(team){
            if(!team.version) team.version = 1000;
        })
        returnData.data = teamList;
    },
    createTeam : function (){
        var name = this.data.name;
        var teamData = this.documentTeam.getPersonTeam(name,this.person)
        if(!teamData.id){
            teamData = this.documentTeam.save(this.data);
            var aclData = {
                "person" : this.person,
                "acl" : 0,
                "documentId" : teamData.id
            }
            this.documentAcl.save(aclData);
            this.documentLog.addLog(this.person,"添加团队",teamData.id,name)
        }
    },
    updateTeam : function (){
        var teamId = this.data.id;
        var teamData = this.documentTeam.getPersonTeamById(teamId,this.person);
        if(teamData.id){
            if(this.data.name){
                teamData.name = this.data.name;
            }
            if(this.data.desc){
                teamData.desc = this.data.desc;
            }
            if(this.data.icon){
                teamData.icon = this.data.icon;
            }
            if(this.data.top){
                teamData.top = this.data.top;
            }
            teamData = this.documentTeam.save(teamData);
            this.documentLog.addLog(this.person,"更新团队",teamData.id)
        }
    },
    removeTeam : function (){
        var teamId = this.data.teamId;
        var teamData = this.documentTeam.getPersonTeamById(teamId,this.person)
        if(teamData.id){
            var folderList = this.documentFolder.getAllFolder(teamId);
            folderList.each(function (folder){
                //获取文件夹下的所有文档
                //然后删除文档
                var documentList = this.document.getFolderDocument(folder.id,this.person);
                documentList.each(function (d){
                    this._removeDocument(d.id);
                }.bind(this));

                this.documentFolder.delete(folder.id);
                this.documentLog.addLog(data.person,"删除文件夹",folder.id);
            }.bind(this));
            this.documentLog.addLog(this.person,"删除团队",teamData.id)
        }
    },
    getParentFolder : function (){
        var folderId = this.data.folderId;
        var folderData = this.documentFolder.get(folderId);
        if(folderData.id){
            var parentFolderData = this.documentFolder.get(folderData.parentId);
            returnData.data = parentFolderData;
        }
    },
    callback : function(){
        //onlyoffice 回调
        print("onlyoffice callback")
        var action = this.data.action;
        print("action:" + action)

        if(action === "modify" || action === "add"){
            this.updateDocument();
            this.closeDocument();
        }
        if(action === "close"){
            this.closeDocument();
        }
        if(action === "open"){
            this.openDocument();
        }

        print(JSON.stringify(this.data))
    },
    test : function(){
        // var dd = this.documentLog.save({
        //     "documentName" : "哈哈哈哈"
        // })
        dd = this.documentFolder.getAllFolder("21a4f5c0-e71c-4c12-bc4c-9f40449392f6")
        returnData.data = dd;
    },

});
new CloudDocument.Main(fun,data);
this.response.setBody(returnData,"application/json");