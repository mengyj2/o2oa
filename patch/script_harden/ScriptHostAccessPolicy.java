package com.x.base.core.project.scripting;

import org.graalvm.polyglot.HostAccess;

/**
 * 服务端脚本宿主访问收敛策略（安全补丁）。
 *
 * 背景：O2OA 10.0.2 的 GraalvmScriptingFactory.eval 使用
 * Context.allowHostAccess(HostAccess.ALL)，导致脚本一旦持有任意宿主对象
 * （平台把大量 com.x.* 对象绑进脚本作用域），即可通过反射链
 * Class -> getMethod -> Method.invoke 越权执行 Runtime.exec 等，构成 RCE（CVE 类沙箱逃逸）。
 * allowHostClassLookup 仅做类名层拦截（allowClass/denyClassList），反射链可绕过 —— 单靠黑名单不够。
 *
 * 本类的两个职责：
 *  1) hardenedHostAccess()：以 HostAccess.ALL 为基线保证业务脚本兼容，再显式 denyAccess
 *     反射 API 与 RCE/文件系统/网络/类加载/线程/数据库 等危险宿主类，彻底掐断反射越权链。
 *     （不使用裸 HostAccess.EXPLICIT：那样会令所有绑定宿主对象的公共成员不可调用，搞瘫业务脚本。）
 *  2) isDangerousClass(String)：供 allowClass 前置判定，fail-closed 拒绝危险类/包，
 *     作为 Java.type 层的纵深防御。
 */
public class ScriptHostAccessPolicy {

    /** 危险类前缀（含反射、IO、Net、SQL、invoke 等包） */
    private static final String[] DANGEROUS_PREFIXES = {
            "java.lang.reflect.",
            "java.lang.invoke.",
            "java.io.",
            "java.nio.file.",
            "java.net.",
            "java.sql.",
            "javax.script.",
            "javax.xml.",
            "org.w3c.dom."
    };

    /** 危险精确类名（RCE / 进程 / 系统 / 类加载 / 线程 / 反射 / 文件系统 / 网络 / 数据库） */
    private static final String[] DANGEROUS_EXACT = {
            "java.lang.Runtime",
            "java.lang.ProcessBuilder",
            "java.lang.Process",
            "java.lang.System",
            "java.lang.ClassLoader",
            "java.lang.Thread",
            "java.lang.ThreadGroup",
            "java.lang.RuntimePermission",
            "java.lang.SecurityManager",
            "java.lang.reflect.Method",
            "java.lang.reflect.Field",
            "java.lang.reflect.Constructor",
            "java.lang.reflect.AccessibleObject",
            "java.lang.reflect.Modifier",
            "java.lang.reflect.Proxy",
            "java.lang.reflect.InvocationHandler",
            "java.io.File",
            "java.io.FileInputStream",
            "java.io.FileOutputStream",
            "java.io.RandomAccessFile",
            "java.nio.file.Files",
            "java.nio.file.Paths",
            "java.nio.file.Path",
            "java.net.URL",
            "java.net.URLClassLoader",
            "java.net.Socket",
            "java.net.ServerSocket",
            "java.net.InetAddress",
            "java.net.NetworkInterface",
            "java.net.MulticastSocket",
            "java.sql.DriverManager",
            "java.sql.Connection",
            "java.sql.Statement",
            "java.sql.PreparedStatement"
    };

    /** Java.type / 宿主类查找层：危险类直接拒绝（fail-closed）。 */
    public static boolean isDangerousClass(String className) {
        if (className == null || className.isEmpty()) {
            return true;
        }
        for (String e : DANGEROUS_EXACT) {
            if (e.equals(className)) {
                return true;
            }
        }
        for (String p : DANGEROUS_PREFIXES) {
            if (className.startsWith(p)) {
                return true;
            }
        }
        return false;
    }

    /**
     * 收敛后的宿主访问策略：以 HostAccess.ALL 为基线（保证业务脚本对绑定宿主对象的公共成员、
     * List/Iterable/Array/Buffer 等访问完全兼容），仅显式 deny 危险类与反射 API。
     * 这样即使脚本通过绑定对象取得了 Class 引用，也无法调用 Class.getMethod/Method.invoke
     * 等反射入口，更无法触达 Runtime/ProcessBuilder/System/ClassLoader 等敏感宿主类。
     */
    public static HostAccess hardenedHostAccess() {
        HostAccess.Builder builder = HostAccess.newBuilder(HostAccess.ALL);
        builder.denyAccess(java.lang.Runtime.class);
        builder.denyAccess(java.lang.ProcessBuilder.class);
        builder.denyAccess(java.lang.Process.class);
        builder.denyAccess(java.lang.System.class);
        builder.denyAccess(java.lang.ClassLoader.class);
        builder.denyAccess(java.lang.Thread.class);
        builder.denyAccess(java.lang.ThreadGroup.class);
        builder.denyAccess(java.lang.RuntimePermission.class);
        builder.denyAccess(java.lang.SecurityManager.class);
        builder.denyAccess(java.lang.reflect.Method.class);
        builder.denyAccess(java.lang.reflect.Field.class);
        builder.denyAccess(java.lang.reflect.Constructor.class);
        builder.denyAccess(java.lang.reflect.AccessibleObject.class);
        builder.denyAccess(java.lang.reflect.Modifier.class);
        builder.denyAccess(java.lang.reflect.Proxy.class);
        builder.denyAccess(java.lang.reflect.InvocationHandler.class);
        builder.denyAccess(java.io.File.class);
        builder.denyAccess(java.io.FileInputStream.class);
        builder.denyAccess(java.io.FileOutputStream.class);
        builder.denyAccess(java.io.RandomAccessFile.class);
        builder.denyAccess(java.nio.file.Files.class);
        builder.denyAccess(java.nio.file.Paths.class);
        builder.denyAccess(java.nio.file.Path.class);
        builder.denyAccess(java.net.URL.class);
        builder.denyAccess(java.net.URLClassLoader.class);
        builder.denyAccess(java.net.Socket.class);
        builder.denyAccess(java.net.ServerSocket.class);
        builder.denyAccess(java.net.InetAddress.class);
        builder.denyAccess(java.net.NetworkInterface.class);
        builder.denyAccess(java.net.MulticastSocket.class);
        builder.denyAccess(java.sql.DriverManager.class);
        builder.denyAccess(java.sql.Connection.class);
        builder.denyAccess(java.sql.Statement.class);
        builder.denyAccess(java.sql.PreparedStatement.class);
        return builder.build();
    }
}
