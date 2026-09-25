#!/bin/sh
# O2OA 本地管理员工具（容器内执行，纯离线）
# 用法：
#   o2admin.sh token              生成 20 分钟有效的 cipher token（管理员 API 用）
#   o2admin.sh login <用户名> <密码>  测试登录
#   o2admin.sh mkperson <名> <密码>   创建普通人员（管理员 API，需先 token）
#   o2admin.sh setpwd <标识> <新密码>  修改某人密码
set -e
D=/opt/o2server
CLS="$D/admin-tools/classes"
JARS=""
for j in $D/store/jars/*.jar $D/commons/ext_java11/*.jar; do JARS="$JARS:$j"; done
JAVA=$D/jvm/linux_java11/bin/java
BASE=http://127.0.0.1:9090
CMD="${1:-token}"

mktoken() {
  $JAVA -cp "$CLS$JARS" -Duser.dir=$D MkToken 2>/dev/null
}

case "$CMD" in
  token)
    mktoken; echo
    ;;
  login)
    U="${2:?用户名}"; P="${3:?密码}"
    curl -s -X POST -H "Content-Type: application/json" \
      --data-binary "{\"credential\":\"$U\",\"password\":\"$P\"}" \
      "$BASE/x_organization_assemble_authentication/jaxrs/authentication"
    echo
    ;;
  mkperson)
    N="${2:?名称}"; P="${3:?密码}"; T=$(mktoken)
    curl -s -X POST -H "x-token: $T" -H "Content-Type: application/json" \
      --data-binary "{\"name\":\"$N\",\"unique\":\"$N\",\"password\":\"$P\",\"mobile\":\"13900000000\",\"mail\":\"$N@local.host\",\"employee\":\"$N\"}" \
      "$BASE/x_organization_assemble_control/jaxrs/person"
    echo
    ;;
  setpwd)
    F="${2:?标识}"; P="${3:?新密码}"; T=$(mktoken)
    curl -s -X POST -H "x-token: $T" -H "Content-Type: application/json" \
      --data-binary "{\"value\":\"$P\"}" \
      "$BASE/x_organization_assemble_control/jaxrs/person/$F/set/password/mockputtopost"
    echo
    ;;
  *) echo "未知命令: $CMD"; exit 1 ;;
esac
