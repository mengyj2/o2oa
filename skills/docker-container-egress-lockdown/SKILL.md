---
name: docker-container-egress-lockdown
description: 让 Docker 容器彻底无法访问外网（含 IP 直连），同时保留宿主端口访问与容器间通信。当用户问"怎么让容器不能联网""DNS 隔离够不够""容器偷偷连外网怎么办""能上外网但不让某服务通信""internal 网络导致端口 502""iptables 封容器出站"时调用。覆盖 DNS 隔离的漏洞实测、iptables FORWARD 封堵、internal 网络的 502 陷阱、以及容器内应用外连能力的取证方法。
agent_created: true
category: security
---

# Docker 容器出站封网（彻底断外网但保留宿主访问）

## 0. 先认清一个常见误区

**`dns: [不存在的解析器]` 只挡域名解析，挡不住 IP 直连。**

实测（O2OA 容器）：
```bash
docker exec <c> curl -s -o /dev/null -w '%{http_code}' https://www.o2oa.net  # → 000  挡住了
docker exec <c> curl -s -o /dev/null -w '%{http_code}' http://223.5.5.5      # → 404  ⚠️ 通了！
```
容器只要还有默认路由（`cat /proc/net/route` 里 `Destination=00000000`），
**任何已知 IP 都能直连出网**。所以 DNS 隔离是"软屏蔽"，不是安全边界。

## 1. 为什么不能用 `internal: true` 网络

`internal` 网络确实能彻底断外网（无默认路由 → `Network is unreachable`），
但 **Docker Desktop 对 internal 网络不做 DNAT**，端口映射直接失效：

```bash
docker network create t --internal
docker run -d --network t -p 18080:80 nginx
curl localhost:18080        # → 502（容器起来了，但宿主访问不通）
```

**结论**：需要"宿主能访问 + 容器不能出网"时，必须走 iptables，不能用 internal。

## 2. 正解：iptables 按容器 IP 丢出站

```bash
# 只放通 Docker 内网段（含 mysql 等），其余一律丢
iptables -I FORWARD 1 -s <容器IP> ! -d 172.16.0.0/12 \
  -m comment --comment mylock -j DROP
```

要点：
- **必须用 `filter` 表 / `FORWARD` 链**。用 `nat` 表会报
  `The "nat" table is not intended for filtering, the use of DROP is therefore inhibited`。
- `172.16.0.0/12` 覆盖 172.16~172.31，足以涵盖 Docker 各类 bridge 子网，同时排除公网。
- 加 `-m comment --comment <tag>`，之后可**按 tag 精确增删**（否则容器重建后找不到旧规则）。
- 入站（宿主 → 端口）不受影响，因为宿主访问走 DNAT，规则只匹配 `-s <容器IP>` 的出站。

### 在 Docker Desktop on Windows 上怎么执行 iptables
宿主的 iptables 在 Docker Desktop 的 VM 里，**宿主 shell 里没有**。借一个特权容器：
```bash
docki() {  # 建议封装成函数
  docker run --rm --privileged --net=host alpine:latest sh -c \
    "apk add --no-cache iptables >/dev/null 2>&1 && $*"
}
docki "iptables -L FORWARD -n --line-numbers"
```

### 按容器名动态解析 IP（关键，别硬编码）
```bash
IP=$(docker inspect <容器名> --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' | tr ' ' '\n' | grep -E '^[0-9]' | head -1)
```
容器重建后 IP 会变，所以脚本必须每次重新解析 + 先清旧规则再加新规则（幂等）。

## 3. 完整脚本骨架（幂等 + 可逆 + 自验证）

```bash
CONTAINER="<容器名>"; TAG="mylock"; ALLOW_DST="172.16.0.0/12"

ipt() { docker run --rm --privileged --net=host alpine:latest sh -c \
  "apk add --no-cache iptables >/dev/null 2>&1 && $*" 2>/dev/null; }

clear_mine() {   # 按 comment 精确删除，循环到删净为止
  for _ in $(seq 1 20); do
    N=$(ipt "iptables -L FORWARD -n --line-numbers | grep '$TAG' | head -1" | awk '{print $1}')
    [ -n "$N" ] || break
    ipt "iptables -D FORWARD $N"
  done
}

IP=$(docker inspect "$CONTAINER" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' | tr ' ' '\n' | grep -E '^[0-9]' | head -1)
clear_mine
ipt "iptables -I FORWARD 1 -s $IP ! -d $ALLOW_DST -m comment --comment '$TAG' -j DROP"
```

### 验证时避开 curl 的 000 陷阱
`curl` 失败时**自己会打印 000**，若再加 `|| echo 000` 会得到 `"000000"`，
判断就错了。正确写法：
```bash
C=$(docker exec "$CONTAINER" sh -c 'curl -s -o /dev/null -w "%{http_code}" --max-time 6 http://223.5.5.5 2>/dev/null; echo' | tr -d ' \r\n')
case "$C" in ''|*[!0-9]*) C=000 ;; esac
[ "$C" = "000" ] && echo "已封" || echo "未封（$C）"
```

## 4. 验证四件事（缺一不可）

```bash
# ① 外网 IP 直连被挡（这是核心）
docker exec <c> curl ... http://223.5.5.5          # 期望 000
# ② 域名解析失败
docker exec <c> getent hosts www.baidu.com         # 期望失败
# ③ 内网服务仍可达（用 JDBC / 真实客户端，别用 /dev/tcp）
#    ⚠️ 容器里多为 sh(dash)，`/dev/tcp` 是 bash 特性，会误报 "Directory nonexistent"！
# ④ 宿主端口仍可访问
curl -o /dev/null -w '%{http_code}' localhost:<port>   # 期望 200
```

**因果证明**（推荐做）：先测通（如 `404`）→ 加规则 → 测不通（`000`）→
`--remove` → 又通（`404`）。这样能排除"本来就通/不通"的干扰。

**看是否真的拦到包**：
```bash
ipt "iptables -L FORWARD -n -v -x | head -5"   # pkts 列 > 0 才算真拦到
```

## 5. 应用侧加固（可选但推荐）：从配置层再去掉外连地址

内核封网是兜底。如果能同时清掉应用配置里的外连地址，就是双保险
（且用户"临时开网"时也不会立刻外连）。以 O2OA 为例：
```bash
# config/collect.json 里清空云平台/应用打包地址
sed -i -E \
  -e 's|("appPackServerUrl"[[:space:]]*:[[:space:]]*)"[^"]*"|\1""|' \
  -e 's|("appUrl"[[:space:]]*:[[:space:]]*)"[^"]*"|\1""|' \
  -e 's|("server"[[:space:]]*:[[:space:]]*)"[^"]*"|\1""|' collect.json
```
- 改完**必须验证 JSON 仍合法**（用 Python `json.load` 或应用自己的解析器）。
- sed 要避免误伤 `"###key"` 形式的注释字段 —— 用精确键名 + 值模式约束。

## 6. 取证：容器里的应用到底会不会外连

不要凭猜测。系统性扫描：
```bash
# 解压所有 jar，然后扫域名常量
docker exec <c> sh -c 'grep -rhoaE "https?://[a-zA-Z0-9._:-]+" /tmp/scan --include="*.class" \
  | sed -E "s|https?://||;s|/.*||;s|:.*||" | grep -vE "^(127\.0\.0\.1|localhost)$" \
  | sort | uniq -c | sort -rn'
```
- `strings` 在精简镜像里常常**不存在** → 用 `grep -a` 代替。
- 定位某域名属于哪个类：`grep -rla "<域名>" /tmp/scan --include="*.class"`
- **排除噪音**：`java.sun.com` / `www.w3.org` / `apache.org` 是 XML/DTD 命名空间，**不联网**。
- 判断"是否真会外连"要看三处：① 配置里 `enable` 是否为 false；
  ② 谁引用了这个类（`grep -rla <类的路径>`，看是否有定时任务/service）；
  ③ 运行日志里有没有 `unknownhost` / `connectexception` / 外网域名。

## 7. ⚠️ 运维铁律

1. **Docker Desktop 重启后 iptables 规则全部丢失** → 必须重跑脚本。
2. **容器重建/升级后 IP 可能变化** → 也要重跑（脚本会先清旧规则）。
3. 最稳妥：**把封网脚本串进启动脚本**（启动等待就绪后自动调用），避免人工遗忘。
4. 提供 `--check` / `--remove` 子命令，让用户能自己看状态、临时开网。
