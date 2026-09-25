import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.jar.JarEntry;
import java.util.jar.JarInputStream;
import java.util.jar.JarOutputStream;

/**
 * ASM 补丁：改写 x_base_core_project.jar 中的
 * com.x.base.core.project.scripting.GraalvmScriptingFactory
 *
 *  - eval(Source, Bindings)：将 Context.allowHostAccess(HostAccess.ALL)
 *    替换为 allowHostAccess(ScriptHostAccessPolicy.hardenedHostAccess())，
 *    掐断反射越权链（CVE 沙箱逃逸）。
 *  - allowClass(String)：前置 ScriptHostAccessPolicy.isDangerousClass 判定（fail-closed），
 *    作为 Java.type 类名层的纵深防御。
 *
 * 用法：java -cp asm-9.7.jar GraalvmScriptingFactoryHarden <jar路径>
 * 该 jar 会被原地更新；调用方需先备份。
 */
public class GraalvmScriptingFactoryHarden {

    private static final String TARGET_CLASS = "com/x/base/core/project/scripting/GraalvmScriptingFactory.class";
    private static final String POLICY = "com/x/base/core/project/scripting/ScriptHostAccessPolicy";

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: GraalvmScriptingFactoryHarden <jar>");
            System.exit(2);
        }
        File jarFile = new File(args[0]);
        byte[] orig = Files.readAllBytes(jarFile.toPath());

        File tmp = File.createTempFile("sh_patch_", ".jar");
        boolean patched = false;
        try (JarInputStream jis = new JarInputStream(new ByteArrayInputStream(orig));
             JarOutputStream jos = new JarOutputStream(new FileOutputStream(tmp))) {
            JarEntry entry;
            while ((entry = jis.getNextJarEntry()) != null) {
                byte[] data = readAll(jis);
                String name = entry.getName();
                if (TARGET_CLASS.equals(name)) {
                    ClassReader cr = new ClassReader(data);
                    SafeClassWriter cw = new SafeClassWriter(cr);
                    cr.accept(new HardenVisitor(cw), ClassReader.SKIP_FRAMES);
                    data = cw.toByteArray();
                    patched = true;
                    System.out.println("PATCHED " + name);
                }
                if (!entry.isDirectory()) {
                    JarEntry out = new JarEntry(name);
                    out.setTime(entry.getTime());
                    jos.putNextEntry(out);
                    jos.write(data);
                    jos.closeEntry();
                }
            }
        }
        if (!patched) {
            System.err.println("TARGET_CLASS_NOT_FOUND " + TARGET_CLASS);
            tmp.delete();
            System.exit(3);
        }
        Files.move(tmp.toPath(), jarFile.toPath(), StandardCopyOption.REPLACE_EXISTING);
        System.out.println("JAR_UPDATED " + jarFile.getAbsolutePath());
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) != -1) {
            bos.write(buf, 0, n);
        }
        return bos.toByteArray();
    }

    /** ClassWriter 重写 getCommonSuperClass，解析失败安全回退到 java/lang/Object，避免 COMPUTE_FRAMES 抛错。 */
    static class SafeClassWriter extends ClassWriter {
        SafeClassWriter(ClassReader cr) {
            super(cr, ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
        }

        @Override
        protected String getCommonSuperClass(String a, String b) {
            try {
                return super.getCommonSuperClass(a, b);
            } catch (Throwable t) {
                return "java/lang/Object";
            }
        }
    }

    static class HardenVisitor extends ClassVisitor {
        HardenVisitor(ClassVisitor cv) {
            super(Opcodes.ASM9, cv);
        }

        @Override
        public MethodVisitor visitMethod(int access, String name, String descriptor,
                                         String signature, String[] exceptions) {
            MethodVisitor mv = super.visitMethod(access, name, descriptor, signature, exceptions);
            if ("eval".equals(name)
                    && descriptor.contains("GraalvmScriptingFactory$Bindings")
                    && descriptor.endsWith("JsonElement;")) {
                return new EvalVisitor(mv);
            }
            if ("allowClass".equals(name) && "(Ljava/lang/String;)Z".equals(descriptor)) {
                return new AllowClassVisitor(mv);
            }
            return mv;
        }
    }

    /** 将 getstatic HostAccess.ALL 替换为 invokestatic ScriptHostAccessPolicy.hardenedHostAccess() */
    static class EvalVisitor extends MethodVisitor {
        EvalVisitor(MethodVisitor mv) {
            super(Opcodes.ASM9, mv);
        }

        @Override
        public void visitFieldInsn(int opcode, String owner, String name, String descriptor) {
            // 注意：ASM 传入的 owner 是 JVM 内部名（斜杠分隔），不是点分 Java 名
            if (opcode == Opcodes.GETSTATIC
                    && "org/graalvm/polyglot/HostAccess".equals(owner)
                    && "ALL".equals(name)
                    && "Lorg/graalvm/polyglot/HostAccess;".equals(descriptor)) {
                // 将读取 HostAccess.ALL 常量替换为调用策略方法，掐断反射越权链
                mv.visitMethodInsn(Opcodes.INVOKESTATIC, POLICY,
                        "hardenedHostAccess", "()Lorg/graalvm/polyglot/HostAccess;", false);
                return;
            }
            mv.visitFieldInsn(opcode, owner, name, descriptor);
        }
    }

    /** allowClass 前置：若为危险类则直接返回 false（fail-closed）。 */
    static class AllowClassVisitor extends MethodVisitor {
        AllowClassVisitor(MethodVisitor mv) {
            super(Opcodes.ASM9, mv);
        }

        @Override
        public void visitCode() {
            mv.visitCode();
            // if (ScriptHostAccessPolicy.isDangerousClass(className)) return false;
            mv.visitVarInsn(Opcodes.ALOAD, 0);
            mv.visitMethodInsn(Opcodes.INVOKESTATIC, POLICY,
                    "isDangerousClass", "(Ljava/lang/String;)Z", false);
            Label end = new Label();
            mv.visitJumpInsn(Opcodes.IFEQ, end); // 非危险类 -> 继续执行原逻辑
            mv.visitInsn(Opcodes.ICONST_0);
            mv.visitInsn(Opcodes.IRETURN);
            mv.visitLabel(end);
        }
    }
}
