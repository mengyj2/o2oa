import com.x.base.core.project.config.Config;
import com.x.base.core.container.factory.PersistenceXmlHelper;
import java.util.Properties;
import java.util.Enumeration;

public class DiagProps {
    public static void main(String[] args) throws Exception {
        String[] names = {"com.x.base.core.entity.ApplicationBaseEntity",
                          "com.x.program.center.core.entity.Application",
                          "x_program_center", "x_general",
                          "com.x.general.core.entity.GeneralFile"};
        for (String n : names) {
            for (boolean slice : new boolean[]{true, false}) {
                try {
                    Properties p = PersistenceXmlHelper.properties(n, slice);
                    System.out.println("=== properties(\"" + n + "\", " + slice + ") keys:");
                    for (Enumeration<?> e = p.propertyNames(); e.hasMoreElements();) {
                        String k = (String) e.nextElement();
                        System.out.println("    " + k + " = " + p.getProperty(k));
                    }
                } catch (Throwable t) {
                    System.out.println("=== properties(\"" + n + "\", " + slice + ") EX: " + t);
                }
            }
        }
    }
}
