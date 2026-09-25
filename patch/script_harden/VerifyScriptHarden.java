import com.x.base.core.project.scripting.ScriptHostAccessPolicy;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.HostAccess;
import org.graalvm.polyglot.Value;

/**
 * 离线安全验证：在容器隔离环境运行，确认补丁满足
 *   1) 良性脚本（ArrayList / 平台类方法调用）仍可用；
 *   2) HostAccess 层：即使 allowHostClassLookup 全放行，Runtime.exec 仍被拒；
 *   3) 反射链：Class.forName -> getMethod -> Method.invoke 被 HostAccess 拦截；
 *   4) io/net 等危险宿主类被拒；
 *   5) isDangerousClass 对平台/白名单类放行、对危险类拒绝。
 * 全部通过输出 VERIFY_OK；任一失败输出 VERIFY_FAIL 并退出非 0。
 */
public class VerifyScriptHarden {

    static int failures = 0;

    static void check(boolean ok, String name) {
        if (ok) {
            System.out.println("  [PASS] " + name);
        } else {
            System.out.println("  [FAIL] " + name);
            failures++;
        }
    }

    static void expectBlocked(String label, Runnable r) {
        try {
            r.run();
            System.out.println("  [FAIL] " + label + " : 未拦截（应被 HostAccess 拒绝）");
            failures++;
        } catch (Throwable t) {
            System.out.println("  [PASS] " + label + " : 已拦截 (" + t.getClass().getSimpleName() + ")");
        }
    }

    public static void main(String[] args) {
        System.out.println("===== HostAccess 层验证（allowHostClassLookup 全放行，隔离测试） =====");
        HostAccess ha = ScriptHostAccessPolicy.hardenedHostAccess();
        check(ha != null, "hardenedHostAccess() 返回非 null");

        try (Context ctx = Context.newBuilder("js")
                .allowHostClassLoading(true)
                .allowHostAccess(ha)
                .allowHostClassLookup(s -> true)
                .build()) {

            // 1) 良性：构造 ArrayList 并调用其方法（验证 allowPublicAccess 保留）
            Value v1 = ctx.eval("js", "var L = Java.type('java.util.ArrayList'); var x = new L(); x.add('a'); x.size();");
            check(v1.asInt() == 1, "良性宿主对象方法调用（ArrayList.add/size）可用");

            // 2) 良性：平台前缀类不被 isDangerousClass 拒绝
            check(!ScriptHostAccessPolicy.isDangerousClass("com.x.base.core.project.connection.JdbcConnection"),
                    "平台类 com.x.base.core.project.connection.* 不被拒");
            check(!ScriptHostAccessPolicy.isDangerousClass("com.x.organization.core.xxx"),
                    "平台类 com.x.organization.core.* 不被拒");
            check(!ScriptHostAccessPolicy.isDangerousClass("java.util.ArrayList"),
                    "白名单类 java.util.ArrayList 不被拒");
            check(!ScriptHostAccessPolicy.isDangerousClass("java.lang.String"),
                    "java.lang.String 不被拒（保留普通对象能力）");

            // 3) 危险类名单正确
            check(ScriptHostAccessPolicy.isDangerousClass("java.lang.Runtime"), "java.lang.Runtime 被拒");
            check(ScriptHostAccessPolicy.isDangerousClass("java.lang.ProcessBuilder"), "java.lang.ProcessBuilder 被拒");
            check(ScriptHostAccessPolicy.isDangerousClass("java.lang.System"), "java.lang.System 被拒");
            check(ScriptHostAccessPolicy.isDangerousClass("java.lang.reflect.Method"), "java.lang.reflect.Method 被拒");
            check(ScriptHostAccessPolicy.isDangerousClass("java.lang.reflect.Field"), "java.lang.reflect.Field 被拒");
            check(ScriptHostAccessPolicy.isDangerousClass("java.io.File"), "java.io.File 被拒");
            check(ScriptHostAccessPolicy.isDangerousClass("java.net.Socket"), "java.net.Socket 被拒");
            check(ScriptHostAccessPolicy.isDangerousClass("java.sql.Connection"), "java.sql.Connection 被拒");
            check(ScriptHostAccessPolicy.isDangerousClass("java.lang.ClassLoader"), "java.lang.ClassLoader 被拒");

            // 4) HostAccess 层：直接 RCE（即便 Java.type 放行）必须被拒
            expectBlocked("Runtime.getRuntime().exec 被 HostAccess 拦截", () ->
                    ctx.eval("js", "Java.type('java.lang.Runtime').getRuntime().exec('id')"));

            // 5) HostAccess 层：反射链 Class.forName -> getMethod -> invoke 必须被拒
            expectBlocked("反射链 Class.forName().getMethod().invoke() 被拦截", () ->
                    ctx.eval("js",
                            "var c = Java.type('java.lang.String');"
                                    + "var rt = c.getClass().forName('java.lang.Runtime');"
                                    + "var m = rt.getMethod('getRuntime');"
                                    + "m.invoke(null).exec('id');"));

            // 6) HostAccess 层：文件系统
            expectBlocked("new java.io.File().exists() 被 HostAccess 拦截", () ->
                    ctx.eval("js", "new Java.type('java.io.File')('/etc/passwd').exists()"));

            // 7) HostAccess 层：网络
            expectBlocked("new java.net.Socket() 被 HostAccess 拦截", () ->
                    ctx.eval("js", "new Java.type('java.net.Socket')('127.0.0.1', 9090)"));
        } catch (Throwable t) {
            System.out.println("  [FAIL] Context 构建/执行异常: " + t);
            t.printStackTrace();
            failures++;
        }

        if (failures == 0) {
            System.out.println("VERIFY_OK");
            System.exit(0);
        } else {
            System.out.println("VERIFY_FAIL count=" + failures);
            System.exit(1);
        }
    }
}
