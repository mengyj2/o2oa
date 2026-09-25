#!/usr/bin/env bash
# =============================================================================
# o2oa_rebuild_patches.sh —— 数据源补丁重放流水线（在 o2oa 容器内执行）
#
# 作用：从「原始 jar」重新生成三个补丁产物，并离线校验，输出到 /out/
#   ① x_base_core_project.jar : Config.externalDataSources()  → 真正读 JSON
#   ② x_base_core_project.jar : ExternalDataSources.enable()  → 不再硬返回 false
#   ③ console.jar             : ResourceFactory.internal()    → 绑 jdbc/sNNN 到 MySQL
#
# 设计原则：
#   - 只用 O2OA 自带 JDK/javassist/ASM，全程离线
#   - 补丁③ 必须通过 -Xverify:all 离线校验之后才产出
#   - 先体检新版 jar 是否还需要补丁，不需要就明确跳过
#   - 失败时输出明确原因与下一步，绝不产出带病产物
#
# 输入（由调用方准备好）：
#   /in/console.orig.jar            ← 新版原始 console.jar
#   /in/x_base_core_project.orig.jar ← 新版原始 x_base_core_project.jar
# 输出：
#   /out/console.patched.jar
#   /out/x_base_core_project.patched.jar
#   /out/report.txt                ← 体检与结果报告
# =============================================================================
set -u

D=/opt/o2server
JP=$D/jvm/linux_java11/bin
JAVASSIST=$D/commons/ext_java11/javassist-3.21.0-GA.jar
ASM=$D/commons/ext_java11/asm-9.7.jar
GRAAL=$D/commons/module_java11/graal-sdk-22.3.4.jar
SRC=/src            # 补丁 .java 源码挂载点
IN=/in              # 原始 jar 挂载点
OUT=/out            # 产物挂载点
WORK=/work

CJ=$IN/console.orig.jar
XC=$IN/x_base_core_project.orig.jar
REPORT=$OUT/report.txt
: > "$REPORT"

log()  { echo "[$(date +%H:%M:%S)] $*" | tee -a "$REPORT"; }
ok()   { echo "  [OK]   $*" | tee -a "$REPORT"; }
warn() { echo "  [WARN] $*" | tee -a "$REPORT"; }
err()  { echo "  [FAIL] $*" | tee -a "$REPORT"; }

die() { err "$1"; echo "ABORT: $2" | tee -a "$REPORT"; exit 1; }

rm -rf "$WORK"; mkdir -p "$WORK" "$OUT"

# -----------------------------------------------------------------------------
# 0. 前置检查
# -----------------------------------------------------------------------------
log "===== [0/6] 前置检查 ====="
[ -f "$CJ" ] || die "缺少 $CJ（新版原始 console.jar）" "请确认已从新版 zip 提取并放到 in/ 目录"
[ -f "$XC" ] || die "缺少 $XC（新版原始 x_base_core_project.jar）" "请确认已从新版 zip 提取并放到 in/ 目录"
[ -f "$JAVASSIST" ] || die "缺少 javassist: $JAVASSIST" "新版 O2OA 的 commons 目录结构可能变了"
[ -f "$ASM" ] || die "缺少 ASM: $ASM" "新版 O2OA 的 commons 目录结构可能变了"
[ -f "$GRAAL" ] || die "缺少 GraalVM SDK: $GRAAL" "新版 O2OA 的 commons/module_java11 目录结构可能变了"
ok "原始 jar 与依赖齐备"

# --- 版本信息 ---
VER=$(cat "$D/version" 2>/dev/null || echo "unknown")
log "O2OA 版本: $VER"
log "console.orig.jar          md5=$(md5sum "$CJ" | cut -d' ' -f1) size=$(stat -c%s "$CJ")"
log "x_base_core_project.orig  md5=$(md5sum "$XC" | cut -d' ' -f1) size=$(stat -c%s "$XC")"

# -----------------------------------------------------------------------------
# 1. 体检：新版是否还需要这三个补丁
# -----------------------------------------------------------------------------
log ""
log "===== [1/6] 体检新版是否仍需要补丁 ====="

mkdir -p "$WORK/probe"
cd "$WORK/probe" || die "无法进入工作目录" "检查容器权限"

$JP/jar xf "$XC" \
  "com/x/base/core/project/config/Config.class" \
  "com/x/base/core/project/config/ExternalDataSources.class" 2>/dev/null \
  || die "无法从新版 x_base_core_project.jar 解出目标类" "类名可能被重构，请人工确认"

# 1a. Config.externalDataSources() 是否还是 return defaultInstance()
CFG_DUMP=$($JP/javap -p -c com/x/base/core/project/config/Config.class 2>/dev/null \
  | sed -n '/externalDataSources()/,/^$/p')
if echo "$CFG_DUMP" | grep -q "ExternalDataSources.defaultInstance"; then
  NEED_1=yes
  ok "门控① 仍存在（externalDataSources() 返回 defaultInstance）→ 需要补丁"
else
  NEED_1=no
  warn "门控① 未检出 —— 新版可能已修复，跳过补丁①"
  echo "        (javap 摘要: $(echo "$CFG_DUMP" | grep -oE 'Method [^ ]+' | head -3 | tr '\n' ' '))" | tee -a "$REPORT"
fi

# 1b. ExternalDataSources.enable() 是否还是硬返回 false
EDS_DUMP=$($JP/javap -p -c com/x/base/core/project/config/ExternalDataSources.class 2>/dev/null \
  | sed -n '/Boolean enable()/,/^$/p')
if echo "$EDS_DUMP" | grep -qE "iconst_0" && ! echo "$EDS_DUMP" | grep -qE "hasNext|iterator"; then
  NEED_2=yes
  ok "门控② 仍存在（enable() 硬返回 false）→ 需要补丁"
else
  NEED_2=no
  warn "门控② 未检出 —— 新版可能已修复，跳过补丁②"
fi

# 1c. ResourceFactory.internal() 是否还把 jdbc/字母 绑到 H2
mkdir -p "$WORK/probe2"
cd "$WORK/probe2" || die "无法进入工作目录" "检查容器权限"
$JP/jar xf "$CJ" "com/x/server/console/ResourceFactory.class" 2>/dev/null \
  || die "无法从新版 console.jar 解出 ResourceFactory" "类名可能被重构，请人工确认"

RF_DUMP=$($JP/javap -p com/x/server/console/ResourceFactory.class 2>/dev/null)
if echo "$RF_DUMP" | grep -q "internalDriudC3p0"; then
  NEED_3=yes
  ok "门控③ 仍存在（internal() 走 internalDriudC3p0，绑 H2）→ 需要补丁"
else
  NEED_3=no
  warn "门控③ 未检出 —— 新版可能已重构 ResourceFactory，跳过补丁③"
  echo "        新版 ResourceFactory 方法清单：" | tee -a "$REPORT"
  echo "$RF_DUMP" | grep -E "public|private|protected" | sed 's/^/          /' | tee -a "$REPORT"
fi

echo "NEED_1=$NEED_1 NEED_2=$NEED_2 NEED_3=$NEED_3" >> "$REPORT"
log "体检结果: 补丁①=$NEED_1  补丁②=$NEED_2  补丁③=$NEED_3"

# -----------------------------------------------------------------------------
# 2. 生成 x_base_core_project.patched.jar（补丁①②）
# -----------------------------------------------------------------------------
log ""
log "===== [2/6] x_base_core_project.jar 补丁 ====="

cp "$XC" "$WORK/xc.jar"

if [ "$NEED_1" = "yes" ] || [ "$NEED_2" = "yes" ]; then
  cd "$WORK" || die "cd 失败" "检查容器权限"
  mkdir -p cls
  CP="$JAVASSIST"

  for P in ConfigPatch2 ExternalDataSourcesPatch; do
    SRCJAVA="$SRC/$P.java"
    [ -f "$SRCJAVA" ] || die "缺少补丁源码 $SRCJAVA" "确认 patch/ 目录已挂载到 /src"
    $JP/javac -cp "$CP" -d cls "$SRCJAVA" \
      || die "$P.java 编译失败" "新版 javassist API 可能变化，需人工调整"
  done
  ok "补丁类编译完成"

  # ConfigPatch2 签名: main(jarPath)，注意它内部 jar 路径取 args[0]
  if [ "$NEED_1" = "yes" ]; then
    # ConfigPatch2 硬编码 outDir=/tmp/patched2 并直接 jar uf 到 args[0]
    $JP/java -cp "$JAVASSIST:cls" ConfigPatch2 "$WORK/xc.jar" > "$WORK/cfg.log" 2>&1
    if grep -q "jar update rc=0" "$WORK/cfg.log"; then
      ok "补丁① 注入成功"
    else
      err "补丁① 注入失败："
      sed 's/^/          /' "$WORK/cfg.log" | tee -a "$REPORT"
      die "补丁① 失败" "新版 Config.externalDataSources() 结构已变，需人工重新实现"
    fi
  fi

  if [ "$NEED_2" = "yes" ]; then
    $JP/java -cp "$JAVASSIST:cls" ExternalDataSourcesPatch "$WORK/xc.jar" > "$WORK/eds.log" 2>&1
    if grep -q "jar update rc=0" "$WORK/eds.log"; then
      ok "补丁② 注入成功"
    else
      err "补丁② 注入失败："
      sed 's/^/          /' "$WORK/eds.log" | tee -a "$REPORT"
      die "补丁② 失败" "新版 ExternalDataSources.enable() 结构已变，需人工重新实现"
    fi
  fi

  # 回读验证：确认两个方法确实被改了
  mkdir -p "$WORK/vfy" && cd "$WORK/vfy" || die "cd 失败" "检查容器权限"
  $JP/jar xf "$WORK/xc.jar" \
    "com/x/base/core/project/config/Config.class" \
    "com/x/base/core/project/config/ExternalDataSources.class"

  V1=$($JP/javap -p -c com/x/base/core/project/config/Config.class 2>/dev/null \
    | sed -n '/externalDataSources()/,/^$/p')
  if echo "$V1" | grep -q "readConfigObject"; then
    ok "回读校验① 通过（已改为 readConfigObject）"
  else
    die "回读校验① 失败：补丁未生效" "请把 report.txt 发出来人工分析"
  fi

  V2=$($JP/javap -p -c com/x/base/core/project/config/ExternalDataSources.class 2>/dev/null \
    | sed -n '/Boolean enable()/,/^$/p')
  if echo "$V2" | grep -qE "hasNext|iterator"; then
    ok "回读校验② 通过（已改为遍历判定）"
  else
    die "回读校验② 失败：补丁未生效" "请把 report.txt 发出来人工分析"
  fi
else
  warn "①② 均判定为不需要 —— 直接用原始 jar"
fi

cp "$WORK/xc.jar" "$OUT/x_base_core_project.patched.jar"
ok "产出: x_base_core_project.patched.jar"

# -----------------------------------------------------------------------------
# 2b. 脚本沙箱 HostAccess 收敛（CVE 反射越权修复；恒需，不随版本跳过）
#     GraalvmScriptingFactory.eval 用 Context.allowHostAccess(HostAccess.ALL)
#     → 脚本持任何宿主对象即可 Class.forName().getMethod().invoke() 反射越权。
#     此处把 HostAccess.ALL 收敛为 ScriptHostAccessPolicy.hardenedHostAccess()
#     （以 ALL 为基线逐项 denyAccess 危险类），并给 allowClass 前置
#     isDangerousClass 类名层纵深防御。策略类 + 离线安全验证见 patch/script_harden/。
# -----------------------------------------------------------------------------
log ""
log "===== [2b] 脚本沙箱 HostAccess 收敛（GraalvmScriptingFactory.eval）====="

cd "$WORK" || die "cd 失败" "检查容器权限"
SH=$SRC/script_harden
[ -f "$SH/GraalvmScriptingFactoryHarden.java" ] || die "缺少 $SH/GraalvmScriptingFactoryHarden.java" "确认 patch/script_harden/ 已挂载到 /src"
[ -f "$SH/ScriptHostAccessPolicy.java" ]        || die "缺少 $SH/ScriptHostAccessPolicy.java" "确认 patch/script_harden/ 已挂载到 /src"
[ -f "$SH/VerifyScriptHarden.java" ]            || die "缺少 $SH/VerifyScriptHarden.java" "确认 patch/script_harden/ 已挂载到 /src"

rm -rf shcls; mkdir -p shcls
log "编译脚本沙箱补丁（ASM + GraalVM SDK）..."
$JP/javac -cp "$ASM:$GRAAL" -d shcls \
  "$SH/GraalvmScriptingFactoryHarden.java" \
  "$SH/ScriptHostAccessPolicy.java" \
  "$SH/VerifyScriptHarden.java" \
  || die "脚本沙箱补丁编译失败" "新版 ASM/GraalVM SDK 版本可能变化，需人工调整"
ok "编译完成"

log "ASM 改写 eval（HostAccess.ALL -> hardenedHostAccess）+ allowClass 前置..."
$JP/java -cp "$ASM:shcls" GraalvmScriptingFactoryHarden "$OUT/x_base_core_project.patched.jar" > sh.log 2>&1
if [ $? -ne 0 ]; then
  err "ASM 改写失败，输出："
  sed 's/^/          /' sh.log | tee -a "$REPORT"
  die "脚本沙箱补丁失败" "新版 GraalvmScriptingFactory 结构可能已变，需人工重新分析 eval 方法"
fi
ok "ASM 改写完成"

# 注入策略类
( cd shcls && $JP/jar uf "$OUT/x_base_core_project.patched.jar" \
    com/x/base/core/project/scripting/ScriptHostAccessPolicy.class ) \
  || die "注入 ScriptHostAccessPolicy.class 失败" "检查容器内 jar 工具"
ok "已注入 ScriptHostAccessPolicy.class"

# 回读校验：eval 必须真的调 hardenedHostAccess，且 allowClass 前置 isDangerousClass，
# 且 eval 内不得残留 getstatic HostAccess.ALL（否则等于没收敛，等于裸 ALL）。
rm -rf shvfy && mkdir shvfy && cd shvfy || die "cd 失败" "检查容器权限"
$JP/jar xf "$OUT/x_base_core_project.patched.jar" com/x/base/core/project/scripting/GraalvmScriptingFactory.class
$JP/javap -p -c com/x/base/core/project/scripting/GraalvmScriptingFactory.class 2>/dev/null > eval.txt
EVAL_OK=$(grep -c "ScriptHostAccessPolicy.hardenedHostAccess" eval.txt)
ALLOW_OK=$(grep -c "ScriptHostAccessPolicy.isDangerousClass" eval.txt)
EVAL_RESIDUAL=$(awk '/eval\(/{f=1} f{print} f&&/^$/{exit}' eval.txt | grep -c "HostAccess.ALL")
if [ "$EVAL_OK" -ge 1 ] && [ "$ALLOW_OK" -ge 1 ] && [ "$EVAL_RESIDUAL" -eq 0 ]; then
  ok "回读校验通过（eval->hardenedHostAccess, allowClass->isDangerousClass, HostAccess.ALL 残留=$EVAL_RESIDUAL）"
else
  err "回读校验失败（EVAL_OK=$EVAL_OK ALLOW_OK=$ALLOW_OK RESIDUAL=$EVAL_RESIDUAL）"
  die "脚本沙箱硬化未生效" "新版 GraalvmScriptingFactory 方法结构可能已变，需人工重新分析"
fi
cd "$WORK" || exit 1

# 离线安全验证（复刻 O2OA 的 GraalVM JVMCI 启动参数）：
# RCE/反射链/IO/Net/SQL 必须被拦截，良性 ArrayList/String/平台类必须零回归。
log "离线 JVM 安全验证（-Xverify:all + GraalVM 模块）..."
GRAAL_MOD=$D/commons/module_java11
CPV="$WORK/shcls:$OUT/x_base_core_project.patched.jar"
for j in $D/store/jars/*.jar $D/commons/ext_java11/*.jar $D/commons/*.jar; do
  CPV="$CPV:$j"
done
$JP/java -XX:+UnlockExperimentalVMOptions -XX:+EnableJVMCI \
  --module-path=$GRAAL_MOD \
  --upgrade-module-path=$GRAAL_MOD/compiler.jar:$GRAAL_MOD/compiler-management.jar \
  -Xverify:all -cp "$CPV" VerifyScriptHarden > shverify.log 2>&1
if grep -q "VERIFY_OK" shverify.log; then
  ok "VERIFY_OK —— 危险类/反射链/IO/Net/SQL 全拦截，良性脚本零回归"
else
  err "离线安全验证未通过，输出："
  tail -40 shverify.log | sed 's/^/          /' | tee -a "$REPORT"
  die "脚本沙箱安全验证失败" "新版类结构导致硬化策略行为异常，需人工排查 VerifyScriptHarden"
fi

# -----------------------------------------------------------------------------
# 3. console.jar 补丁③：ASM 重写 + 离线校验
# -----------------------------------------------------------------------------
log ""
log "===== [3/6] console.jar 补丁③（ASM）====="

if [ "$NEED_3" != "yes" ]; then
  warn "补丁③ 判定为不需要 —— 直接用原始 console.jar"
  cp "$CJ" "$OUT/console.patched.jar"
else
  cd "$WORK" || die "cd 失败" "检查容器权限"
  rm -rf asm; mkdir -p asm
  cd asm || die "cd 失败" "检查容器权限"

  cp "$CJ" ./console.orig.jar
  cp "$SRC/ResourceFactoryAsmPatch.java" . || die "缺少 ResourceFactoryAsmPatch.java" "确认 patch/ 已挂载到 /src"
  cp "$SRC/VerifyCls.java" .             || die "缺少 VerifyCls.java" "确认 patch/ 已挂载到 /src"

  log "编译 ASM 补丁..."
  $JP/javac -cp "$ASM" -d . ResourceFactoryAsmPatch.java VerifyCls.java \
    || die "ASM 补丁编译失败" "新版 ASM 版本或 API 不匹配，需人工调整"
  ok "编译完成"

  # ★ ResourceFactoryAsmPatch 内部硬编码把补丁类写到 /tmp/rfasm/，
  #   所以必须先清空该目录，执行后从那里取产物（不能假定是 cwd）。
  ASMOUT=/tmp/rfasm
  rm -rf "$ASMOUT"

  log "对原始 jar 执行 ASM 重写（此处失败通常意味着方法结构已变）..."
  $JP/java -cp "$ASM:." ResourceFactoryAsmPatch ./console.orig.jar > asm.log 2>&1
  if [ $? -ne 0 ]; then
    err "ASM 重写失败，输出："
    sed 's/^/          /' asm.log | tee -a "$REPORT"
    die "补丁③ 失败" "新版 ResourceFactory.internal() 结构已变 —— 需人工重新分析该方法，报告见 out/report.txt"
  fi
  ok "ASM 重写完成"

  PATCHED_CLS="$ASMOUT/com/x/server/console/ResourceFactory.class"
  if [ ! -f "$PATCHED_CLS" ]; then
    err "ASM 未产出补丁类（期望 $PATCHED_CLS）"
    echo "        实际 /tmp 下产物:" | tee -a "$REPORT"
    find /tmp -name "ResourceFactory.class" 2>/dev/null | sed 's/^/          /' | tee -a "$REPORT"
    die "补丁③ 产物缺失" "新版补丁输出路径可能已改，需人工确认 ResourceFactoryAsmPatch 的写出位置"
  fi
  ok "补丁类已产出: $PATCHED_CLS"

  # 组完整 classpath 做离线 JVM 校验：
  #   $ASMOUT (补丁类) + $WORK/asm (VerifyCls 自身) 都要在，否则找不到主类
  CP="$ASMOUT:$WORK/asm:$CJ:$XC"
  for j in $D/store/jars/*.jar $D/commons/ext_java11/*.jar $D/commons/*.jar; do
    CP="$CP:$j"
  done

  log "离线 JVM 校验（-Xverify:all）..."
  $JP/java -Xverify:all -cp "$CP" VerifyCls > vfy.log 2>&1
  if grep -q "VERIFY_OK" vfy.log; then
    ok "VERIFY_OK —— 字节码合法"
    # 注入到工作副本（用子 shell 切到补丁类根目录，避免污染 cwd）
    ( cd "$ASMOUT" && $JP/jar uf "$WORK/asm/console.orig.jar" com/x/server/console/ResourceFactory.class ) \
      || die "注入 console.jar 失败" "检查容器内 jar 工具"
    ok "已注入到 console.patched.jar"

    # 回读确认
    rm -rf rb && mkdir rb && cd rb || die "cd 失败" "检查容器权限"
    $JP/jar xf ../console.orig.jar com/x/server/console/ResourceFactory.class
    if $JP/javap -p com/x/server/console/ResourceFactory.class 2>/dev/null | grep -q "internalDriudC3p0_external"; then
      ok "回读校验③ 通过（新增 internalDriudC3p0_external 已存在）"
    else
      die "回读校验③ 失败" "字节码未按预期改动，报告见 out/report.txt"
    fi
    cd .. || exit 1
    cp ./console.orig.jar "$OUT/console.patched.jar"
    ok "产出: console.patched.jar"
  else
    err "离线校验未通过，输出："
    tail -40 vfy.log | sed 's/^/          /' | tee -a "$REPORT"
    die "补丁③ 校验失败（VerifyError）" "新版方法结构/Java 版本导致 StackMapTable 不匹配 —— 需人工调整 ASM 帧，报告见 out/report.txt"
  fi
fi

# -----------------------------------------------------------------------------
# 4. 产物汇总
# -----------------------------------------------------------------------------
log ""
log "===== [4/6] 产物汇总 ====="
for f in console.patched.jar x_base_core_project.patched.jar; do
  if [ -f "$OUT/$f" ]; then
    log "  $f  md5=$(md5sum "$OUT/$f" | cut -d' ' -f1)  size=$(stat -c%s "$OUT/$f")"
  else
    die "产物缺失: $f" "见上面的失败信息"
  fi
done

# -----------------------------------------------------------------------------
# 5. 校验产物与原始 jar 的差异（确保真的改了）
# -----------------------------------------------------------------------------
log ""
log "===== [5/6] 差异确认 ====="
for pair in "console.orig.jar:console.patched.jar" "x_base_core_project.orig.jar:x_base_core_project.patched.jar"; do
  A="${pair%%:*}"; B="${pair##*:}"
  MA=$(md5sum "$IN/$A" | cut -d' ' -f1)
  MB=$(md5sum "$OUT/$B" | cut -d' ' -f1)
  if [ "$MA" = "$MB" ]; then
    warn "$B 与原始 jar 完全相同（该 jar 未做任何改动）"
  else
    ok "$B 与原始 jar 不同（已改动）"
  fi
done

log ""
log "===== [6/6] 完成 ====="
log "产物目录: $OUT"
log "报告文件: $REPORT"
log ""
log "※ 关于产物 md5：jar uf 会向 jar 内写入当前时间戳，因此【同一份源码重打两次，"
log "  产物 md5 也会不同】——这是正常的，不代表内容变了。判断两版产物是否等价，"
log "  要比对【类文件的字节 md5】（unzip 出 .class 再 md5sum），而非 jar 整体 md5。"
echo "PIPELINE_OK" | tee -a "$REPORT"
