import java.io.*;
import java.lang.reflect.*;

/**
 * Loads the patched ResourceFactory.class bytes and forces full JVM bytecode verification
 * WITHOUT restarting O2OA. Throws VerifyError/ClassFormatError if the patch is bad.
 */
public class VerifyCls {
    public static void main(String[] args) throws Exception {
        String path = args.length > 0 ? args[0] : "/tmp/rfasm/com/x/server/console/ResourceFactory.class";
        byte[] b = readAll(new File(path));
        System.out.println("bytes=" + b.length);
        // Custom loader: define WITHOUT linking, then force verification via linking.
        class Probe extends ClassLoader {
            Probe(ClassLoader p) { super(p); }
            Class<?> define(byte[] bb) { return defineClass("com.x.server.console.ResourceFactory", bb, 0, bb.length, null); }
        }
        Probe cl = new Probe(VerifyCls.class.getClassLoader());
        Class<?> c = cl.define(b);
        System.out.println("defined: " + c.getName());
        // Force verification + resolution of the methods we care about.
        for (Method m : c.getDeclaredMethods()) {
            System.out.println("  method: " + m);
        }
        System.out.println("VERIFY_OK");
    }
    static byte[] readAll(File f) throws IOException {
        try (InputStream is = new FileInputStream(f)) {
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[8192]; int n;
            while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
            return bos.toByteArray();
        }
    }
}
