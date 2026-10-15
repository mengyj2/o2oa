import {lp} from '@o2oa/component';
function getMenuJson(){
    return [
        {
            'title': lp.baseConfig,
            "icon": "config",
            "expand": true,
            'children': [
                {'title': lp.systemInfo, 'component': 'BaseSystemInfo', 'icon': 'config', "expand": true},
                {'title': lp.uiConfig, 'component': 'BaseUIConfig', 'icon': 'ui'},
                // {'title': lp.componentDeploy, 'component': 'ComponentDeploy', 'icon': 'component'},
                {'title': lp.resourceDeploy, 'component': 'BaseResourceDeploy', 'icon': 'upload' }
                // {'title': lp.resourceDeploy, 'component': 'WebDeploy', 'icon': 'upload' },
                // {'title': lp.serviceDeploy, 'component': 'ServiceDeploy', 'icon': 'deploy' }
            ]
        },
        {
            // 用户定制（CCIA 多租户品牌定制，2026-10-15 新增）
            // 位置：基础配置 与 服务配置 之间（用户明确要求）。
            // 职责：可视化维护组织名称、系统页脚、品牌 Logo、站点图标等"租户级"品牌项。
            // 落库：组织类写官方 config/collect.json（持久卷）；图形类走 DeployAction
            //      部署到持久 webroot（持久卷），可通过 Http 访问。
            // 文案直接内联中文（本部署为中文单语，避免动 108KB 的 lp 语言包）。
            'title': '用户定制',
            "icon": "color",
            "expand": true,
            'children': [
                {'title': '品牌标识', 'component': 'SysCustomBrand', 'icon': 'color', "expand": true}
            ]
        },
        {
            'title': lp.serverConfig,
            "icon": "servers",
            'children': [
                {'title': lp.serversConfig, 'component': 'ServerServersConfig', 'icon': 'service' },
                // {'title': lp.centerServer, 'component': '', 'icon': 'center' },
                // {'title': lp.appServer, 'component': '', 'icon': 'service' },
                // {'title': lp.webServer, 'component': '', 'icon': 'web' },
                
                {'title': lp.storageServer, 'component': 'ServerStorageConfig', 'icon': 'download' },
                {'title': lp.cloudConfig, 'component': 'ServerCloudConfig', 'icon': 'cloud' },
                {'title': lp.processConfig, 'component': 'ServerProcessConfig', 'icon': 'flow' },

                {'title': lp.messageConfig, 'component': 'ServerMessageConfig', 'icon': 'message' },
                {'title': lp.queryIndexConfig, 'component': 'ServerQueryConfig', 'icon': 'search' },
                {'title': lp.cacheConfig, 'component': 'ServerCacheConfig', 'icon': 'cache' },
                // {'title': lp.clusterConfig, 'component': '', 'icon': 'servers' },
                // {'title': lp.orgConfig, 'component': '', 'icon': 'org' },


                // {'title': lp.dumpConfig, 'component': '', 'icon': 'dump' },
                {'title': lp.worktimeConfig, 'component': 'ServerWorktimeConfig', 'icon': 'timer' }
            ]
        },
        {
            'title': lp.securityConfig,
            "icon": "security",
            'children': [
                {'title': lp.passwordConfig, 'component': 'SecurityPasswordConfig', 'icon': 'password' },
                {'title': lp.loginConfig, 'component': 'SecurityLoginConfig', 'icon': 'signin' },
                {'title': lp.ssoConfig, 'component': 'SecuritySSOConfig', 'icon': 'sso' },
                {'title': lp.ternaryManagement, 'component': 'SecurityTernaryConfig', 'icon': 'log' }
            ]
        },
        // {
        //     'title': lp.messageConfig,
        //     "icon": "message",
        //     'children': [
        //         {'title': lp.msgTypeConfig, 'component': '', 'icon': 'message' },
        //
        //         {'title': lp.mailConfig, 'component': '', 'icon': 'mail' },
        //         {'title': lp.smsConfig, 'component': '', 'icon': 'sms' },
        //         {'title': lp.mqConfig, 'component': '', 'icon': 'mq' }
        //     ]
        // },
        {
            'title': lp.mobileConfig,
            "icon": "mobile",
            'children': [
                {'title': lp.appConfig, 'component': 'MobileAppConfig', 'icon': 'connect' },
                {'title': lp.pushConfig, 'component': 'MobilePushConfig', 'icon': 'push' },
                // {'title': lp.moduleConfig, 'component': '', 'icon': 'apps' },
                // {'title': lp.iconConfig, 'component': '', 'icon': 'icon' },
                {'title': lp.integrationConfig, 'component': 'MobileIntegrationConfig', 'icon': 'dingding' },
                // {'title': lp.wechatConfig, 'component': '', 'icon': 'wechat' },
                // {'title': lp.welinkConfig, 'component': '', 'icon': 'welink' },
                {'title': lp.appTools, 'component': 'MobileToolsConfig', 'icon': 'tools' }
            ]
        }
    ];
}

export {getMenuJson};
