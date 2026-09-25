# O2OA 本地账号与登录说明（离线 / 不触发官方服务器）

## 一、登录凭据（当前）

| 项 | 值 |
|---|---|
| 访问地址 | http://localhost:9090 |
| 用户名 | `xadmin` |
| 密码 | `o2oaadmin2026` |
| 身份 | 系统管理员（manager），拥有 4 个内置管理角色 |

> 密码来源：容器内 `config/token.json` 的 `password` 字段
> （存储为 `(ENCRYPT:...)`，用 O2OA 自带 `Crypto.plainText()` 解密得到明文）。

## 二、为什么是 xadmin：它不是数据库里的用户

O2OA 的初始管理员是**虚拟账号**，**不写入** `ORG_PERSON` 表，只在登录时由
`Config.token()` 实时校验：

```
ActionLogin.execute():
  if (Config.token().isInitialManager(credential)) {       // credential == "xadmin"
      if (!Config.token().verifyPassword(credential, password)) throw ...
      wo = this.manager(...);                              // 直接签发 manager token
  } else {
      // 走数据库查 ORG_PERSON + 校验 xpassword
  }
```

相关硬编码常量（`com.x.base.core.project.config.Token`）：

| 常量 | 值 |
|---|---|
| `defaultInitialManager` | `xadmin` |
| `defaultInitialManagerDistinguishedName` | `xadmin@o2oa@P` |
| `initPassword` | `o2oa@2022`（当 token.json 密码为空时的兜底） |
| `surfix` | `o2platform`（DES key 来源，取前 8 字节 `o2platfo`） |

所以：**新建人员时不能用 `xadmin` 这个名字**（会报
`ExceptionInitialManagerName`「不能使用初始管理员标识」）。

## 三、xadmin 的密码怎么改

**只能改 `config/token.json`**。接口层明确拒绝：

```
PUT /x_organization_assemble_control/jaxrs/person/xadmin/set/password
→ {"message":"请通过控制台修改初始管理员密码.",
   "prompt":"...ExceptionDenyChangeInitialManagerPassword"}
```

改法（推荐，纯离线）：

```bash
# 1) 生成新的 (ENCRYPT:...) 值（容器内执行）
docker exec -it o2oa-server sh -c '
  cd /opt/o2server/admin-tools
  cat > Enc.java <<EOF
import com.x.base.core.project.tools.Crypto;
public class Enc {
  public static void main(String[] a) throws Exception {
    System.out.print(Crypto.formattedDefaultEncrypt(a[0]));
  }
}
EOF
D=/opt/o2server; JCP="."
for j in $D/store/jars/*.jar $D/commons/ext_java11/*.jar; do JCP="$JCP:$j"; done
$D/jvm/linux_java11/bin/javac -cp "$JCP" -d classes Enc.java
$D/jvm/linux_java11/bin/java -cp "classes$JCP" Enc "你的新密码"
'

# 2) 把输出写回 config/token.json 的 password 字段
#    （host 侧文件：D:\O2OA\o2server\config\token.json 若已挂载；
#      否则 docker exec 内用 sed 修改 /opt/o2server/config/token.json）

# 3) 重启容器
docker restart o2oa-server
```

## 四、日常账号运维（o2admin.sh）

脚本位置：容器内 `/opt/o2server/admin-tools/o2admin.sh`（已随镜像固化）。

```bash
# 生成 20 分钟有效的 cipher token（调用管理员 API 用）
docker exec o2oa-server /opt/o2server/admin-tools/o2admin.sh token

# 测试某个账号能否登录
docker exec o2oa-server /opt/o2server/admin-tools/o2admin.sh login xadmin o2oaadmin2026

# 创建普通人员
docker exec o2oa-server /opt/o2server/admin-tools/o2admin.sh mkperson zhangsan Zhang@12345

# 修改某人密码
docker exec o2oa-server /opt/o2server/admin-tools/o2admin.sh setpwd zhangsan NewPwd@2026
```

## 五、cipher token 的构造原理（为什么能免登录调管理员接口）

1. O2OA 的 token 格式（`HttpToken.who` 里的正则）：
   ```
   ^(anonymous|user|manager|cipher|systemManager|securityManager|auditManager)
    ([2][0][1-9]\d[0-1]\d[0-3]\d[0-5]\d[0-5]\d[0-5]\d)     # yyyyMMddHHmmss
    (h5|moa|app)?(\S{1,})$
   ```
2. `CipherManagerJaxrsFilter.doFilter` 调用：
   ```java
   new HttpToken().who(request, response, Config.token().getCipher());
   ```
   第三个参数 `cipher` 就是 `HttpToken.who` 里 `Crypto.decrypt(token, cipher, encryptType)` 的 **key**。
3. 因此构造：`"cipher" + 当前时间戳 + md5Hex(token.json密码)`，
   用 `Crypto.encrypt(token, cipher, "")`（DES，key 取 `cipher` 前 8 字节）加密，
   放进 `x-token` 头即可通过 `CipherManagerJaxrsFilter`（有效期 20 分钟）。

`MkToken.java` 就是干这个的——它直接调用 O2OA 自己的 `Config` / `Crypto`，
所以格式永远正确，无需手工推算。

## 六、登录不联网的保证

容器网络已做离线隔离（`docker-compose.yml`）：

- `dns: [127.0.0.1]` → 容器内所有外网域名解析失败（O2OA 对外通信全靠域名）。
- `extra_hosts: ["mysql:<IP>"]` → 容器间 `mysql` 走静态解析，不受影响。
- 网络为普通 `bridge`（**不是** `internal: true`），保证宿主机 `localhost:9090` 端口映射正常。

实测：容器内 `curl http://www.o2oa.net` → `000`（不通）；`getent hosts mysql` → `172.22.0.2`；
宿主 `curl localhost:9090` → `200`。登录动作只读写本地 MySQL + token.json，无任何外发。
