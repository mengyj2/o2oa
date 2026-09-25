import javassist.*;
import java.io.File;

/**
 * 修复 O2OA 10.0.2 x_base_core_project.jar 中 Config.externalDataSources() 的硬编码缺陷（v2: 无条件读文件）。
 * 原始(坏)实现: return ExternalDataSources.defaultInstance();  —— 永远 enable=false, 无视 config/externalDataSources.json。
 * 修复后: 每次都读取 config/externalDataSources.json（读不到才回退 defaultInstance）。
 * 不复用实例字段缓存，彻底绕开 Config 构造函数从旧 INSTANCE 拷贝字段、regenerate 重置等干扰。
 */
public class ConfigPatch2 {
    public static void main(String[] args) throws Exception {
        String jar = "/opt/o2server/store/jars/x_base_core_project.jar";
        if (args.length > 0) jar = args[0];
        String javassistJar = "/opt/o2server/commons/ext_java11/javassist-3.21.0-GA.jar";
        String outDir = "/tmp/patched2";

        ClassPool cp = ClassPool.getDefault();
        cp.insertClassPath(jar);
        cp.insertClassPath(javassistJar);

        CtClass cc = cp.get("com.x.base.core.project.config.Config");
        CtMethod m = cc.getDeclaredMethod("externalDataSources");

        String body = "{"
            + " com.x.base.core.project.config.ExternalDataSources obj ="
            + "   (com.x.base.core.project.config.ExternalDataSources)"
            + "   com.x.base.core.project.tools.BaseTools.readConfigObject("
            + "     PATH_CONFIG_EXTERNALDATASOURCES,"
            + "     com.x.base.core.project.config.ExternalDataSources.class);"
            + " if (obj == null) obj = com.x.base.core.project.config.ExternalDataSources.defaultInstance();"
            + " return obj;"
            + "}";

        m.setBody(body);

        cc.writeFile(outDir);
        cc.detach();

        String cls = "com/x/base/core/project/config/Config.class";
        Process p = Runtime.getRuntime().exec(new String[]{
            "/opt/o2server/jvm/linux_java11/bin/jar", "uf", jar, "-C", outDir, cls
        });
        int rc = p.waitFor();
        System.out.println("jar update rc=" + rc);
        System.out.println("Patched(always-read): " + jar);
    }
}
