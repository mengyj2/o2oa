import org.objectweb.asm.*;
import java.io.*;
import java.util.jar.*;

/**
 * Patch #3 for O2OA console.jar.
 *
 * PROBLEM
 * -------
 * console.jar's com.x.server.console.ResourceFactory.internal() binds the JNDI name
 * "jdbc/<letter>" to an *H2 TCP* DataSource, derived from Config.nodes().dataServers().
 * With externalDataSources enabled, O2OA's data layer (PersistenceXmlHelper
 * .propertiesExternalSlice) instead asks OpenJPA to resolve
 *     openjpa.slice.<name>.ConnectionFactoryName = "jdbc/<name>"
 * where <name> comes from ExternalDataSources.names() and looks like "s001".
 * So the JNDI resource O2OA actually looks up is "jdbc/s001", NOT "jdbc/X".
 * Result: no matching DataSource -> OpenJPA falls back to persistence.xml and fails with
 *   "A JDBC driver or data source class name must be specified".
 *
 * FIX
 * ---
 * internal() is rewritten to call a new internalDriudC3p0_external() which:
 *   - builds ONE MySQL DruidDataSourceC3P0Adapter from Config.externalDataSources().get(0)
 *   - binds it to "jdbc/<name>" for every name returned by ExternalDataSources.names()
 *     (i.e. jdbc/s001, jdbc/s002, ...)  <- what OpenJPA actually asks for
 *   - ALSO binds the legacy slice letters jdbc/B..jdbc/Z as a safety net.
 *
 * Bytecode strategy: COMPUTE_MAXS only; every emitted method body is hand-framed.
 * The names() loop uses an explicit StackMapTable frame at the loop head.
 */
public class ResourceFactoryAsmPatch {
    static final String RF = "com/x/server/console/ResourceFactory";
    static final String EXT = "com/x/base/core/project/config/ExternalDataSource";
    static final String EXTS = "com/x/base/core/project/config/ExternalDataSources";
    static final String CFG = "com/x/base/core/project/config/Config";
    static final String C3P0 = "com/alibaba/druid/pool/DruidDataSourceC3P0Adapter";
    static final String DRUID = "com/alibaba/druid/pool/DruidDataSource";
    static final String RES = "org/eclipse/jetty/plus/jndi/Resource";
    static final String FU = "org/apache/commons/lang3/reflect/FieldUtils";
    // slice letters used by internal mode (matches SlicePropertiesBuilder constant)
    static final String LETTERS = "BCDEFGHIJKLMNOPQRSTUVWXYZ";

    public static void main(String[] args) throws Exception {
        // IMPORTANT: read from the PRISTINE jar, never from an already-patched one,
        // otherwise the new method collides with a previous injection.
        String jar = args.length > 0 ? args[0] : "/tmp/rfasm/console.orig.jar";
        String entry = "com/x/server/console/ResourceFactory.class";
        byte[] orig = readEntry(jar, entry);
        if (orig == null) { System.out.println("NOT FOUND " + entry + " in " + jar); return; }

        ClassWriter cw = new ClassWriter(ClassWriter.COMPUTE_MAXS) {
            @Override
            protected String getCommonSuperClass(String a, String b) {
                try { return super.getCommonSuperClass(a, b); }
                catch (Throwable t) { return "java/lang/Object"; }
            }
        };
        ClassVisitor cv = new ClassVisitor(Opcodes.ASM9, cw) {
            @Override
            public MethodVisitor visitMethod(int access, String name, String descriptor,
                                             String signature, String[] exceptions) {
                MethodVisitor mv = super.visitMethod(access, name, descriptor, signature, exceptions);
                if ("internal".equals(name) && "()V".equals(descriptor)) {
                    return new InternalRewriter(Opcodes.ASM9, mv);
                }
                return mv;
            }
            @Override
            public void visitEnd() {
                MethodVisitor mv = cw.visitMethod(
                    Opcodes.ACC_PRIVATE | Opcodes.ACC_STATIC,
                    "internalDriudC3p0_external", "()Ljava/util/List;", null,
                    new String[]{"java/lang/Exception"});
                genExternal(mv);
                super.visitEnd();
            }
        };
        new ClassReader(orig).accept(cv, ClassReader.EXPAND_FRAMES);

        byte[] out = cw.toByteArray();
        File outCls = new File("/tmp/rfasm/com/x/server/console/ResourceFactory.class");
        outCls.getParentFile().mkdirs();
        try (FileOutputStream fos = new FileOutputStream(outCls)) { fos.write(out); }
        System.out.println("PATCHED class bytes=" + out.length);
    }

    static byte[] readEntry(String jar, String entry) throws Exception {
        JarFile jf = new JarFile(jar);
        try {
            java.util.Enumeration<JarEntry> en = jf.entries();
            while (en.hasMoreElements()) {
                JarEntry je = en.nextElement();
                if (je.getName().equals(entry)) {
                    try (InputStream is = jf.getInputStream(je)) {
                        ByteArrayOutputStream bos = new ByteArrayOutputStream();
                        byte[] buf = new byte[8192]; int n;
                        while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
                        return bos.toByteArray();
                    }
                }
            }
        } finally { jf.close(); }
        return null;
    }

    /** internal() -> { internalDriudC3p0_external(); }  (linear, one frame at entry) */
    static class InternalRewriter extends MethodVisitor {
        InternalRewriter(int api, MethodVisitor mv) { super(api, mv); }
        @Override public void visitCode() {
            mv.visitCode();
            mv.visitFrame(Opcodes.F_NEW, 0, new Object[0], 0, new Object[0]);
            mv.visitMethodInsn(Opcodes.INVOKESTATIC, RF, "internalDriudC3p0_external",
                    "()Ljava/util/List;", false);
            mv.visitInsn(Opcodes.POP);
            mv.visitInsn(Opcodes.RETURN);
        }
        @Override public void visitInsn(int o){}
        @Override public void visitIntInsn(int o,int v){}
        @Override public void visitVarInsn(int o,int v){}
        @Override public void visitTypeInsn(int o,String t){}
        @Override public void visitFieldInsn(int o,String a,String n,String d){}
        @Override public void visitMethodInsn(int o,String a,String n,String d,boolean i){}
        @Override public void visitInvokeDynamicInsn(String n,String d,Handle b,Object... x){}
        @Override public void visitJumpInsn(int o,Label l){}
        @Override public void visitLabel(Label l){}
        @Override public void visitLdcInsn(Object c){}
        @Override public void visitIincInsn(int v,int i){}
        @Override public void visitTableSwitchInsn(int a,int b,Label d,Label... l){}
        @Override public void visitLookupSwitchInsn(Label d,int[] k,Label[] l){}
        @Override public void visitMultiANewArrayInsn(String d,int n){}
        @Override public void visitTryCatchBlock(Label s,Label e,Label h,String t){}
        @Override public void visitLocalVariable(String n,String d,String s,Label a,Label b,int i){}
        @Override public void visitLineNumber(int l,Label s){}
        @Override public void visitFrame(int t,int n,Object[] l,int s,Object[] k){}
        @Override public void visitMaxs(int a,int b){ mv.visitMaxs(a,b); }
        @Override public void visitEnd(){ mv.visitEnd(); }
    }

    /**
     * internalDriudC3p0_external():
     *   ExternalDataSource ds = Config.externalDataSources().get(0);
     *   DruidDataSourceC3P0Adapter druid = new DruidDataSourceC3P0Adapter();
     *   ... configure from ds ...
     *   DruidDataSource inner = (DruidDataSource) FieldUtils.readField(druid,"dataSource",true);
     *   ... tune inner ...
     *   for (String n : Config.externalDataSources().names()) new Resource("jdbc/"+n, druid);
     *   for (String L : {B..Z})                              new Resource("jdbc/"+L, druid);
     *   return new ArrayList();
     *
     * Locals: 2=ds(ExternalDataSource) 3=druid(C3P0Adapter) 4=names(List) 5=inner(DruidDataSource)
     *         6=iterator(Iterator) 7=name(String)
     */
    static void genExternal(MethodVisitor mv) {
        mv.visitCode();
        // [0] ds = Config.externalDataSources().get(0)
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, CFG, "externalDataSources",
                "()L" + EXTS + ";", false);
        mv.visitInsn(Opcodes.ICONST_0);
        mv.visitMethodInsn(Opcodes.INVOKEINTERFACE, "java/util/List", "get",
                "(I)Ljava/lang/Object;", true);
        mv.visitTypeInsn(Opcodes.CHECKCAST, EXT);
        mv.visitVarInsn(Opcodes.ASTORE, 2);

        // DIAGNOSTIC: System.out.println("[PATCH3] internalDriudC3p0_external entered, url=" + ds.getUrl());
        mv.visitFieldInsn(Opcodes.GETSTATIC, "java/lang/System", "out", "Ljava/io/PrintStream;");
        mv.visitTypeInsn(Opcodes.NEW, "java/lang/StringBuilder");
        mv.visitInsn(Opcodes.DUP);
        mv.visitLdcInsn("[PATCH3] internalDriudC3p0_external entered url=");
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, "java/lang/StringBuilder", "<init>", "(Ljava/lang/String;)V", false);
        mv.visitVarInsn(Opcodes.ALOAD, 2);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, EXT, "getUrl", "()Ljava/lang/String;", false);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/lang/StringBuilder", "append",
                "(Ljava/lang/String;)Ljava/lang/StringBuilder;", false);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/lang/StringBuilder", "toString",
                "()Ljava/lang/String;", false);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/io/PrintStream", "println",
                "(Ljava/lang/String;)V", false);

        // [1] druid = new DruidDataSourceC3P0Adapter()
        mv.visitTypeInsn(Opcodes.NEW, C3P0);
        mv.visitInsn(Opcodes.DUP);
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, C3P0, "<init>", "()V", false);
        mv.visitVarInsn(Opcodes.ASTORE, 3);

        // driver / url / user / password
        call1(mv, "setDriverClass", "(Ljava/lang/String;)V", EXT, "getDriverClassName");
        call1(mv, "setJdbcUrl",     "(Ljava/lang/String;)V", EXT, "getUrl");
        call1(mv, "setUser",        "(Ljava/lang/String;)V", EXT, "getUsername");
        call1(mv, "setPassword",    "(Ljava/lang/String;)V", EXT, "getPassword");

        // maxPoolSize = ds.getMaxTotal().intValue()  (guard against null)
        mv.visitVarInsn(Opcodes.ALOAD, 3);
        mv.visitVarInsn(Opcodes.ALOAD, 2);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, EXT, "getMaxTotal", "()Ljava/lang/Integer;", false);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/lang/Integer", "intValue", "()I", false);
        mVoid(mv, "setMaxPoolSize", "(I)V");
        // minPoolSize = ds.getMaxIdle().intValue()
        mv.visitVarInsn(Opcodes.ALOAD, 3);
        mv.visitVarInsn(Opcodes.ALOAD, 2);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, EXT, "getMaxIdle", "()Ljava/lang/Integer;", false);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/lang/Integer", "intValue", "()I", false);
        mVoid(mv, "setMinPoolSize", "(I)V");
        // setAcquireIncrement(1)
        mv.visitVarInsn(Opcodes.ALOAD, 3);
        mv.visitInsn(Opcodes.ICONST_1);
        mVoid(mv, "setAcquireIncrement", "(I)V");

        // [2] inner = (DruidDataSource) FieldUtils.readField(druid, "dataSource", true)
        mv.visitVarInsn(Opcodes.ALOAD, 3);
        mv.visitLdcInsn("dataSource");
        mv.visitInsn(Opcodes.ICONST_1);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, FU, "readField",
                "(Ljava/lang/Object;Ljava/lang/String;Z)Ljava/lang/Object;", false);
        mv.visitTypeInsn(Opcodes.CHECKCAST, DRUID);
        mv.visitVarInsn(Opcodes.ASTORE, 5);

        boolean1(mv, 5, "setTestWhileIdle", true);
        boolean1(mv, 5, "setTestOnBorrow", false);
        boolean1(mv, 5, "setTestOnReturn", false);
        str1(mv, 5, "setValidationQuery", "SELECT 1");
        long1(mv, 5, "setTimeBetweenEvictionRunsMillis", 60000L);
        long1(mv, 5, "setMinEvictableIdleTimeMillis", 300000L);
        long1(mv, 5, "setMaxWait", 60000L);

        // [3] for (String n : Config.externalDataSources().names()) new Resource("jdbc/"+n, druid);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, CFG, "externalDataSources",
                "()L" + EXTS + ";", false);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, EXTS, "names", "()Ljava/util/List;", false);
        mv.visitVarInsn(Opcodes.ASTORE, 4);

        Label lCond = new Label(), lBody = new Label();
        mv.visitVarInsn(Opcodes.ALOAD, 4);
        mv.visitMethodInsn(Opcodes.INVOKEINTERFACE, "java/util/List", "iterator",
                "()Ljava/util/Iterator;", true);
        mv.visitVarInsn(Opcodes.ASTORE, 6);
        mv.visitLabel(lCond);
        // frame at loop head. static method, so slots 0/1 are unused -> TOP.
        // locals: [0]=TOP [1]=TOP [2]=ExternalDataSource [3]=C3P0Adapter
        //         [4]=List [5]=DruidDataSource [6]=Iterator
        mv.visitFrame(Opcodes.F_NEW, 7,
                new Object[]{ Opcodes.TOP, Opcodes.TOP, EXT, C3P0,
                              "java/util/List", DRUID, "java/util/Iterator" },
                0, new Object[0]);
        mv.visitVarInsn(Opcodes.ALOAD, 6);
        mv.visitMethodInsn(Opcodes.INVOKEINTERFACE, "java/util/Iterator", "hasNext", "()Z", true);
        mv.visitJumpInsn(Opcodes.IFEQ, lBody);
        mv.visitVarInsn(Opcodes.ALOAD, 6);
        mv.visitMethodInsn(Opcodes.INVOKEINTERFACE, "java/util/Iterator", "next", "()Ljava/lang/Object;", true);
        mv.visitTypeInsn(Opcodes.CHECKCAST, "java/lang/String");
        mv.visitVarInsn(Opcodes.ASTORE, 7);
        // DIAGNOSTIC: System.out.println("[PATCH3] binding jdbc/" + n);
        mv.visitFieldInsn(Opcodes.GETSTATIC, "java/lang/System", "out", "Ljava/io/PrintStream;");
        mv.visitTypeInsn(Opcodes.NEW, "java/lang/StringBuilder");
        mv.visitInsn(Opcodes.DUP);
        mv.visitLdcInsn("[PATCH3] binding jdbc/");
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, "java/lang/StringBuilder", "<init>", "(Ljava/lang/String;)V", false);
        mv.visitVarInsn(Opcodes.ALOAD, 7);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/lang/StringBuilder", "append",
                "(Ljava/lang/String;)Ljava/lang/StringBuilder;", false);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/lang/StringBuilder", "toString",
                "()Ljava/lang/String;", false);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/io/PrintStream", "println",
                "(Ljava/lang/String;)V", false);
        // new Resource("jdbc/" + n, druid)
        mv.visitTypeInsn(Opcodes.NEW, RES);
        mv.visitInsn(Opcodes.DUP);
        mv.visitTypeInsn(Opcodes.NEW, "java/lang/StringBuilder");
        mv.visitInsn(Opcodes.DUP);
        mv.visitLdcInsn("jdbc/");
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, "java/lang/StringBuilder", "<init>", "(Ljava/lang/String;)V", false);
        mv.visitVarInsn(Opcodes.ALOAD, 7);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/lang/StringBuilder", "append",
                "(Ljava/lang/String;)Ljava/lang/StringBuilder;", false);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/lang/StringBuilder", "toString",
                "()Ljava/lang/String;", false);
        mv.visitVarInsn(Opcodes.ALOAD, 3);
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, RES, "<init>", "(Ljava/lang/String;Ljava/lang/Object;)V", false);
        mv.visitInsn(Opcodes.POP);
        // also bind the bare name "s001" (some OpenJPA paths resolve without the jdbc/ prefix)
        mv.visitTypeInsn(Opcodes.NEW, RES);
        mv.visitInsn(Opcodes.DUP);
        mv.visitVarInsn(Opcodes.ALOAD, 7);
        mv.visitVarInsn(Opcodes.ALOAD, 3);
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, RES, "<init>", "(Ljava/lang/String;Ljava/lang/Object;)V", false);
        mv.visitInsn(Opcodes.POP);
        mv.visitJumpInsn(Opcodes.GOTO, lCond);
        mv.visitLabel(lBody);
        // frame after loop: locals: [0]=TOP [1]=TOP [2]=ExtDS [3]=C3P0 [4]=List [5]=Druid [6]=Iterator
        mv.visitFrame(Opcodes.F_NEW, 7,
                new Object[]{ Opcodes.TOP, Opcodes.TOP, EXT, C3P0,
                              "java/util/List", DRUID, "java/util/Iterator" },
                0, new Object[0]);

        // [4] safety net: bind legacy slice letters jdbc/B .. jdbc/Z (and bare letter too)
        for (int i = 0; i < LETTERS.length(); i++) {
            String letter = LETTERS.substring(i, i + 1);
            mv.visitTypeInsn(Opcodes.NEW, RES);
            mv.visitInsn(Opcodes.DUP);
            mv.visitLdcInsn("jdbc/" + letter);
            mv.visitVarInsn(Opcodes.ALOAD, 3);
            mv.visitMethodInsn(Opcodes.INVOKESPECIAL, RES, "<init>", "(Ljava/lang/String;Ljava/lang/Object;)V", false);
            mv.visitInsn(Opcodes.POP);
            mv.visitTypeInsn(Opcodes.NEW, RES);
            mv.visitInsn(Opcodes.DUP);
            mv.visitLdcInsn(letter);
            mv.visitVarInsn(Opcodes.ALOAD, 3);
            mv.visitMethodInsn(Opcodes.INVOKESPECIAL, RES, "<init>", "(Ljava/lang/String;Ljava/lang/Object;)V", false);
            mv.visitInsn(Opcodes.POP);
        }

        // return new ArrayList();
        mv.visitTypeInsn(Opcodes.NEW, "java/util/ArrayList");
        mv.visitInsn(Opcodes.DUP);
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, "java/util/ArrayList", "<init>", "()V", false);
        mv.visitInsn(Opcodes.ARETURN);
        mv.visitMaxs(0, 0);
        mv.visitEnd();
    }

    // ---- helpers: emit  aload3; aload2; invokevirtual owner.getX; invokevirtual C3P0.setX ----
    static void call1(MethodVisitor mv, String setter, String setterDesc, String owner, String getter) {
        mv.visitVarInsn(Opcodes.ALOAD, 3);
        mv.visitVarInsn(Opcodes.ALOAD, 2);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, owner, getter, "()Ljava/lang/String;", false);
        mVoid(mv, setter, setterDesc);
    }
    static void mVoid(MethodVisitor mv, String name, String desc) {
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, C3P0, name, desc, false);
    }
    static void boolean1(MethodVisitor mv, int slot, String setter, boolean v) {
        mv.visitVarInsn(Opcodes.ALOAD, slot);
        mv.visitInsn(v ? Opcodes.ICONST_1 : Opcodes.ICONST_0);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, DRUID, setter, "(Z)V", false);
    }
    static void str1(MethodVisitor mv, int slot, String setter, String v) {
        mv.visitVarInsn(Opcodes.ALOAD, slot);
        mv.visitLdcInsn(v);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, DRUID, setter, "(Ljava/lang/String;)V", false);
    }
    static void long1(MethodVisitor mv, int slot, String setter, long v) {
        mv.visitVarInsn(Opcodes.ALOAD, slot);
        mv.visitLdcInsn(v);
        mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, DRUID, setter, "(J)V", false);
    }
}
