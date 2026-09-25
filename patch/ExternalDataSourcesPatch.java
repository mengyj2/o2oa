import javassist.*;
import java.io.File;

/**
 * 修复 O2OA 10.0.2 x_base_core_project.jar 中 ExternalDataSources.enable() 的硬编码门控。
 *
 * 原始(坏)实现:
 *   public Boolean enable() { return Boolean.FALSE; }   // iconst_0 -> 永远 false
 * 即使用户在 config/externalDataSources.json 配置了 enable:true、MySQL URL 正确，
 * 所有消费方(数据工厂、DataServer 启动守卫、init 恢复)调 .enable() 都拿到 false -> 强制走内置 H2。
 *
 * 修复后: 遍历列表元素, 任一 ExternalDataSource.getEnable() 为真即返回 Boolean.TRUE。
 * 需与 Config.externalDataSources()(无条件读文件) 补丁配合使用。
 */
public class ExternalDataSourcesPatch {
    public static void main(String[] args) throws Exception {
        String jar = "/opt/o2server/store/jars/x_base_core_project.jar";
        if (args.length > 0) jar = args[0];
        String javassistJar = "/opt/o2server/commons/ext_java11/javassist-3.21.0-GA.jar";
        String outDir = "/tmp/eds_patch";

        ClassPool cp = ClassPool.getDefault();
        cp.insertClassPath(jar);
        cp.insertClassPath(javassistJar);

        CtClass cc = cp.get("com.x.base.core.project.config.ExternalDataSources");
        CtMethod m = cc.getDeclaredMethod("enable");

        String body = "{"
            + " for (java.util.Iterator it = this.iterator(); it.hasNext();) {"
            + "   com.x.base.core.project.config.ExternalDataSource item ="
            + "     (com.x.base.core.project.config.ExternalDataSource) it.next();"
            + "   Boolean e = item.getEnable();"
            + "   if (e != null && e.booleanValue()) {"
            + "     return Boolean.TRUE;"
            + "   }"
            + " }"
            + " return Boolean.FALSE;"
            + "}";

        m.setBody(body);

        new File(outDir).mkdirs();
        cc.writeFile(outDir);
        cc.detach();

        String cls = "com/x/base/core/project/config/ExternalDataSources.class";
        Process p = Runtime.getRuntime().exec(new String[]{
            "/opt/o2server/jvm/linux_java11/bin/jar", "uf", jar, "-C", outDir, cls
        });
        int rc = p.waitFor();
        System.out.println("jar update rc=" + rc);
        System.out.println("Patched(enable->real): " + jar);
    }
}
