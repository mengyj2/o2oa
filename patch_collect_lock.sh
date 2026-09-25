#!/bin/bash
# =============================================================================
# O2OA 云平台接口封锁补丁（在 o2oa 容器内执行，幂等）
#
# 目的：把 x_program_center 的 /jaxrs/collect/* 全部接口强制返回 403，
#       物理切断「注册云账号 / 登录云账号 / 找回密码 / 发短信验证码」等外连入口。
#
# 为什么必须打补丁（而不是只靠 config）：
#   x_program_center 的 21 个 collect 接口中，只有 login / validate 两个有
#   `Config.collect().getEnable()` 门控；regist / resetpassword / code 等
#   【完全没有门控】—— 只要容器能联网，就能真的把账号注册到 O2OA 云平台，
#   而且注册成功后会执行 Config.collect().setEnable(true) 自动打开云连接，
#   并立即触发 CollectPerson 上报本机人员的手机号。
#   因此仅在配置层写 enable=false 是不够的，必须在 filter 层物理切断。
#
# 实现：用 javassist 给 com.x.program.center.jaxrs.CollectJaxrsFilter
#       注入一个 doFilter() 覆写 —— 直接 403 返回，永不调用 chain.doFilter()。
#       该类原本只有一个默认构造器，注入非常干净。
#       注入后所有 /jaxrs/collect/* 请求（GET/POST/PUT/DELETE 全部）被拦截。
#
# 影响面（重要）：
#   · collect 模块 : 全部拒绝 —— 这正是我们要的
#   · market  模块 : 不受影响（走 MarketJaxrsFilter，独立）
#   · apppack 模块 : 不受影响（走 AppPackJaxrsFilter，独立）
#   即：应用市场和应用打包功能保持可用（配合临时开闸时使用），
#       但任何人都无法再注册/登录 O2OA 云账号。
#
# 幂等性：每次启动重跑都安全（会先移除已有的 doFilter 再重新注入）。
# 升级安全：O2OA 升级重新部署 war 后，本脚本会把补丁重新打上。
#
# 用法：patch_collect_lock.sh [--verify|--restore|--war]
#   （无参数）  应用补丁到【运行时解包目录】（需 JVM 重启才生效）
#   --war      应用补丁到【store/x_program_center.war】（推荐：构建期用，启动即生效）
#   --verify   只检查补丁状态，不修改
#   --restore  从 .orig 备份恢复原始 class
# =============================================================================
set -u

MODE="${1:-apply}"

D=/opt/o2server
JAVA=$D/jvm/linux_java11/bin/java
JAVAC=$D/jvm/linux_java11/bin/javac
JAVAP=$D/jvm/linux_java11/bin/javap
CP="$D/commons/ext_java11/javassist-3.21.0-GA.jar:$D/commons/ext_java11/javaee-api-8.0.1.jar"

WAR=$D/store/x_program_center.war
WAR_CLS_INNER="WEB-INF/classes/com/x/program/center/jaxrs/CollectJaxrsFilter.class"

WORK=/tmp/collectlock
PATCHER=$WORK/PatchCollectFilter.java
OUT=$WORK/out

# ---- war 模式：直接改写 war 内的 class（构建期用，启动即生效）----
if [ "$MODE" = "--war" ]; then
  rm -rf "$WORK"; mkdir -p "$WORK" "$OUT"

  if [ ! -f "$WAR" ]; then
    echo "[collectlock] ✗ 找不到 $WAR" >&2
    exit 1
  fi

  # ---- 幂等与安全性 ----
  # ① 首次运行：备份原始 war（此后 .orig 始终是「未打补丁」的权威副本）
  # ② 后续运行：先确认 war 是「干净」的，再从干净副本提取，避免在补丁态上叠加
  if [ ! -f "$WAR.orig" ]; then
    cp -f "$WAR" "$WAR.orig"
    echo "[collectlock] 已备份原始 war → $(basename "$WAR").orig"
    WAR_SRC="$WAR"
  else
    # 已有备份：检查 war 当前是否已含补丁
    TMPC=/tmp/collectlock_chk; rm -rf "$TMPC"; mkdir -p "$TMPC"; ( cd "$TMPC"
      if "$D/jvm/linux_java11/bin/jar" xf "$WAR" "$WAR_CLS_INNER" 2>/dev/null \
         && $JAVAP -p "WEB-INF/classes/com/x/program/center/jaxrs/CollectJaxrsFilter.class" 2>/dev/null | grep -q doFilter; then
        echo PATCHED
      else
        echo CLEAN
      fi ) > "$TMPC/state" 2>/dev/null
    STATE=$(cat "$TMPC/state" 2>/dev/null || echo CLEAN)
    rm -rf "$TMPC"
    if [ "$STATE" = "PATCHED" ]; then
      echo "[collectlock] war 已是补丁态，从 .orig 取干净副本重新注入"
      cp -f "$WAR.orig" "$WAR"
    fi
    WAR_SRC="$WAR"
  fi

  # 提取原始 class
  cd "$WORK"
  "$D/jvm/linux_java11/bin/jar" xf "$WAR_SRC" "$WAR_CLS_INNER" 2>/dev/null || {
    echo "[collectlock] ✗ 从 war 提取 class 失败（路径可能已变）" >&2
    exit 1
  }
  EXTRACTED="$WORK/$WAR_CLS_INNER"
  ORIG_WAR_CLS="$WORK/CollectJaxrsFilter.orig.class"
  cp -f "$EXTRACTED" "$ORIG_WAR_CLS"

  echo "[collectlock] 已从 war 提取原始 class"

  # 生成补丁程序
  cat > "$PATCHER" <<'JAVA_EOF'
import javassist.*;
import java.io.*;

public class PatchCollectFilter {
    public static void main(String[] args) throws Exception {
        ClassPool pool = new ClassPool(true);
        pool.appendSystemPath();
        pool.insertClassPath(new LoaderClassPath(PatchCollectFilter.class.getClassLoader()));

        CtClass cc = pool.makeClass(new FileInputStream(args[0]));
        try { cc.removeMethod(cc.getDeclaredMethod("doFilter")); } catch (NotFoundException ignore) { }

        CtClass reqC   = pool.get("javax.servlet.ServletRequest");
        CtClass respC  = pool.get("javax.servlet.ServletResponse");
        CtClass chainC = pool.get("javax.servlet.FilterChain");

        CtMethod m = new CtMethod(CtClass.voidType, "doFilter",
                new CtClass[]{reqC, respC, chainC}, cc);
        m.setModifiers(Modifier.PUBLIC);
        StringBuilder body = new StringBuilder();
        body.append("{\n");
        body.append("  javax.servlet.http.HttpServletResponse _resp = (javax.servlet.http.HttpServletResponse)$2;\n");
        body.append("  _resp.setStatus(403);\n");
        body.append("  _resp.setContentType(\"application/json;charset=UTF-8\");\n");
        body.append("  _resp.getWriter().write(\"{\\\"type\\\":\\\"error\\\",\\\"message\\\":\\\"O2OA collect(o2cloud) interface is disabled by local netlock policy.\\\"}\");\n");
        body.append("  _resp.getWriter().flush();\n");
        body.append("  return;\n");
        body.append("}\n");
        m.setBody(body.toString());
        cc.addMethod(m);
        cc.writeFile(args[1]);
        cc.detach();
        System.out.println("OK");
    }
}
JAVA_EOF

  if ! $JAVAC -cp "$CP" -d "$WORK" "$PATCHER" 2>"$WORK/javac.err"; then
    echo "[collectlock] ✗ 补丁程序编译失败" >&2; cat "$WORK/javac.err" >&2; exit 1
  fi
  if ! $JAVA -cp "$WORK:$CP" PatchCollectFilter "$ORIG_WAR_CLS" "$OUT" 2>"$WORK/java.err"; then
    echo "[collectlock] ✗ 字节码注入失败" >&2; cat "$WORK/java.err" >&2; exit 1
  fi

  PRODUCED="$OUT/com/x/program/center/jaxrs/CollectJaxrsFilter.class"
  [ -f "$PRODUCED" ] || { echo "[collectlock] ✗ 未产出补丁 class" >&2; exit 1; }
  $JAVAP -p "$PRODUCED" 2>/dev/null | grep -q "doFilter" || {
    echo "[collectlock] ✗ 产物校验失败：doFilter 缺失" >&2; exit 1; }

  # 原 war 的备份已在前面按「仅首次」规则完成，这里直接把补丁 class 替换回 war
  cd "$WORK"
  cp -f "$PRODUCED" "$EXTRACTED"
  "$D/jvm/linux_java11/bin/jar" uf "$WAR" "$WAR_CLS_INNER" || {
    echo "[collectlock] ✗ 回写 war 失败" >&2; exit 1; }

  echo "[collectlock] ✓ war 补丁已应用：$WAR"
  echo "[collectlock]   权威原始副本：$(basename "$WAR").orig（请勿删除）"
  rm -rf "$WORK"
  exit 0
fi

# 目标 class：优先 centerServer（运行时解包目录），其次 war 原始位置
CLS_TARGET=""
for c in \
  "$D/servers/centerServer/work/x_program_center/WEB-INF/classes/com/x/program/center/jaxrs/CollectJaxrsFilter.class" \
  "$D/servers/centerServer/x_program_center/WEB-INF/classes/com/x/program/center/jaxrs/CollectJaxrsFilter.class"
do
  if [ -f "$c" ]; then CLS_TARGET="$c"; break; fi
done

log()  { echo "[collectlock] $*"; }
err()  { echo "[collectlock] ✗ $*" >&2; }

ORIG="${CLS_TARGET}.orig"

# ---- 检查模式 ----
if [ "$MODE" = "--verify" ]; then
  # 优先检查 war（这才是权威来源）
  if [ -f "$WAR" ]; then
    TMPV=/tmp/collectlock_verify; rm -rf "$TMPV"; mkdir -p "$TMPV"; cd "$TMPV"
    if "$D/jvm/linux_java11/bin/jar" xf "$WAR" "$WAR_CLS_INNER" 2>/dev/null \
       && $JAVAP -p "WEB-INF/classes/com/x/program/center/jaxrs/CollectJaxrsFilter.class" 2>/dev/null | grep -q "doFilter"; then
      echo "[collectlock] ✓ war 补丁已生效（doFilter 已注入）"
      cd /; rm -rf "$TMPV"; exit 0
    fi
    echo "[collectlock] ✗ war 补丁未生效（doFilter 缺失）"
    cd /; rm -rf "$TMPV"; exit 1
  fi
  # 退而检查运行时解包 class（JVM 已启动的场景）
  if [ -n "$CLS_TARGET" ] && [ -f "$CLS_TARGET" ]; then
    if $JAVAP -p "$CLS_TARGET" 2>/dev/null | grep -q "doFilter"; then
      echo "[collectlock] ✓ 运行时 class 补丁已生效"
      exit 0
    fi
  fi
  echo "[collectlock] ✗ 补丁未生效（war 与运行时 class 均无 doFilter）"
  exit 1
fi

# ---- 以下为应用/恢复模式，必须有目标 class ----
if [ -z "$CLS_TARGET" ]; then
  err "找不到 CollectJaxrsFilter.class（提示：构建期请用 --war 模式）"
  exit 1
fi

# ---- 恢复模式 ----
if [ "$MODE" = "--restore" ]; then
  if [ -f "$ORIG" ]; then
    cp -f "$ORIG" "$CLS_TARGET"
    log "✓ 已从 .orig 恢复原始 class"
    exit 0
  else
    err "找不到备份 $ORIG"
    exit 1
  fi
fi

# ---- 应用模式 ----
rm -rf "$WORK"; mkdir -p "$WORK" "$OUT"

cat > "$PATCHER" <<'JAVA_EOF'
import javassist.*;
import java.io.*;

public class PatchCollectFilter {
    public static void main(String[] args) throws Exception {
        String inPath = args[0];
        String outPath = args[1];

        ClassPool pool = new ClassPool(true);
        pool.appendSystemPath();
        pool.insertClassPath(new LoaderClassPath(PatchCollectFilter.class.getClassLoader()));

        CtClass cc = pool.makeClass(new FileInputStream(inPath));

        try {
            CtMethod old = cc.getDeclaredMethod("doFilter");
            cc.removeMethod(old);
        } catch (NotFoundException ignore) { }

        CtClass reqC   = pool.get("javax.servlet.ServletRequest");
        CtClass respC  = pool.get("javax.servlet.ServletResponse");
        CtClass chainC = pool.get("javax.servlet.FilterChain");

        CtMethod m = new CtMethod(CtClass.voidType, "doFilter",
                new CtClass[]{reqC, respC, chainC}, cc);
        m.setModifiers(Modifier.PUBLIC);

        StringBuilder body = new StringBuilder();
        body.append("{\n");
        body.append("  javax.servlet.http.HttpServletResponse _resp = (javax.servlet.http.HttpServletResponse)$2;\n");
        body.append("  _resp.setStatus(403);\n");
        body.append("  _resp.setContentType(\"application/json;charset=UTF-8\");\n");
        body.append("  _resp.getWriter().write(\"{\\\"type\\\":\\\"error\\\",\\\"message\\\":\\\"O2OA collect(o2cloud) interface is disabled by local netlock policy.\\\"}\");\n");
        body.append("  _resp.getWriter().flush();\n");
        body.append("  return;\n");
        body.append("}\n");

        m.setBody(body.toString());
        cc.addMethod(m);

        cc.writeFile(outPath);
        cc.detach();
        System.out.println("OK");
    }
}
JAVA_EOF

# 1) 备份原始 class（只在首次）
if [ ! -f "$ORIG" ]; then
  cp -f "$CLS_TARGET" "$ORIG"
  log "已备份原始 class → $(basename "$ORIG")"
fi

# 2) 编译补丁程序
if ! $JAVAC -cp "$CP" -d "$WORK" "$PATCHER" 2>"$WORK/javac.err"; then
  err "补丁程序编译失败"; cat "$WORK/javac.err" >&2; exit 1
fi

# 3) 注入
#    注意：源 class 必须是【原始备份】，否则重复注入会叠加
if ! $JAVA -cp "$WORK:$CP" PatchCollectFilter "$ORIG" "$OUT" 2>"$WORK/java.err"; then
  err "字节码注入失败"; cat "$WORK/java.err" >&2; exit 1
fi

PRODUCED="$OUT/com/x/program/center/jaxrs/CollectJaxrsFilter.class"
if [ ! -f "$PRODUCED" ]; then
  err "未产出补丁 class"; exit 1
fi

# 4) 校验后落位
if ! $JAVAP -p "$PRODUCED" 2>/dev/null | grep -q "doFilter"; then
  err "产物校验失败：doFilter 缺失"; exit 1
fi
cp -f "$PRODUCED" "$CLS_TARGET"
log "✓ 补丁已应用：/jaxrs/collect/* 现在全部返回 403"

rm -rf "$WORK"
exit 0
