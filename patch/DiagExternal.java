import com.x.base.core.project.config.Config;
import com.x.base.core.project.config.ExternalDataSources;
import com.x.base.core.project.config.ExternalDataSource;
import com.x.base.core.container.factory.SlicePropertiesBuilder;
import com.x.base.core.container.factory.PersistenceXmlHelper;
import java.util.List;
import java.util.Properties;

public class DiagExternal {
    public static void main(String[] args) throws Exception {
        ExternalDataSources ds = Config.externalDataSources();
        System.out.println("=== Config.externalDataSources() = " + ds);
        System.out.println("=== ds.enable() = " + (ds == null ? "NULL" : ds.enable()));
        if (ds != null) {
            System.out.println("=== size = " + ds.size());
            for (ExternalDataSource o : ds) {
                System.out.println("  item.getEnable() = " + o.getEnable());
                System.out.println("  item.getIncludes() = " + o.getIncludes());
                System.out.println("  item.getExcludes() = " + o.getExcludes());
                System.out.println("  item.getUrl() = " + o.getUrl());
                System.out.println("  name(item) = " + ds.name(o));
            }
            System.out.println("=== ds.names() = " + ds.names());
            System.out.println("=== ds.dictionary() = " + ds.dictionary());
            System.out.println("=== ds.findNamesOfContainerEntity(\"processPlatform\") = " + ds.findNamesOfContainerEntity("processPlatform"));
            System.out.println("=== ds.findNamesOfContainerEntity(\"x_processplatform\") = " + ds.findNamesOfContainerEntity("x_processplatform"));
            System.out.println("=== ds.findNamesOfContainerEntity(\"X\") = " + ds.findNamesOfContainerEntity("X"));
        }
        // which slice name is actually used? try a few likely ones
        String[] guesses = {"processPlatform", "x_processplatform", "x_processplatform_assemble_surface",
                "entityManagerContainer", "x_base", "x_organization", "x_query", "x_cms", "X"};
        for (String g : guesses) {
            try {
                System.out.println("=== findNames(\"" + g + "\") = " + (ds == null ? "n/a" : ds.findNamesOfContainerEntity(g)));
            } catch (Throwable t) {
                System.out.println("=== findNames(\"" + g + "\") EX = " + t);
            }
        }
        // properties for a slice
        for (String g : guesses) {
            try {
                Properties p = PersistenceXmlHelper.properties(g, true);
                System.out.println("=== props(" + g + ", true): driver=" + p.getProperty("javax.persistence.jdbc.driver")
                        + " url=" + p.getProperty("javax.persistence.jdbc.url")
                        + " dict=" + p.getProperty("openjpa.jdbc.DBDictionary"));
            } catch (Throwable t) {
                System.out.println("=== props(" + g + ", true) EX = " + t);
            }
        }
    }
}
