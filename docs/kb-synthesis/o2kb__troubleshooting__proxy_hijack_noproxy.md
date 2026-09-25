# 本地探测代理劫持（curl 假 502）

> category: o2kb::troubleshooting  |  id: o2kb::troubleshooting::proxy_hijack_noproxy

症状：curl http://127.0.0.1:9090 / 18790 等本地地址返回 502，但服务实际在跑。

根因：shell 环境注入了 HTTP(S)_PROXY（本机曾见 52068 端口的代理），curl 默认把 localhost 请求也发往代理，代理连不上本地服务即返 502。

修复：
- 所有本地探测加 `--noproxy "*"`：curl --noproxy "*" -s -o /dev/null -w "%{http_code}" http://127.0.0.1:PORT/
- Python httpx：Client(trust_env=False) 或 proxy=None
- 看门狗/网关启动脚本开头 unset 全部代理变量：HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy= ALL_PROXY= all_proxy= no_proxy="*"
- 判定"服务假死"前先排除代理干扰，避免误判为代码崩。
