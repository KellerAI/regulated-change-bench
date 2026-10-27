package controls;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.lang.reflect.Method;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/** Keeps the test annotations, the JUnit tag and the registry file in step. */
class RegistryConsistencyTest {

    private static final Set<String> COVERAGES = Set.of("exhaustive", "sample");

    @Test
    void annotationsMatchRegistry() throws Exception {
        Map<String, Control> declared = declaredControls();
        Map<String, Object> registry = PolicyFiles.registry();
        assertEquals(new TreeMap<>(registry).keySet(), new TreeMap<>(declared).keySet(), "registered and declared control tests differ");
        for (Map.Entry<String, Control> entry : declared.entrySet()) {
            Map<String, Object> registered = PolicyFiles.object(registry, entry.getKey());
            Control control = entry.getValue();
            assertEquals(registered.get("obligation"), control.obligation(), entry.getKey() + " obligation");
            assertEquals(registered.get("coverage"), control.coverage(), entry.getKey() + " coverage");
            assertEquals(registered.get("domain"), control.domain(), entry.getKey() + " domain");
            assertTrue(COVERAGES.contains(control.coverage()), entry.getKey() + " coverage must be exhaustive or sample");
        }
    }

    @Test
    void controlTestsCarryTheControlTag() throws Exception {
        for (Class<?> type : controlClasses()) {
            Tag tag = type.getAnnotation(Tag.class);
            assertTrue(tag != null && tag.value().equals("control"), type.getName() + " must be tagged control");
        }
    }

    private static Map<String, Control> declaredControls() throws Exception {
        Map<String, Control> declared = new TreeMap<>();
        for (Class<?> type : controlClasses()) {
            for (Method method : type.getDeclaredMethods()) {
                Control control = method.getAnnotation(Control.class);
                if (control != null) {
                    declared.put(type.getName() + "#" + method.getName(), control);
                }
            }
        }
        return declared;
    }

    private static List<Class<?>> controlClasses() throws IOException, URISyntaxException, ClassNotFoundException {
        Path root = Path.of(Control.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        List<String> names;
        try (Stream<Path> files = Files.list(root.resolve("controls"))) {
            names = files.map(file -> file.getFileName().toString())
                    .filter(name -> name.endsWith("ControlTest.class"))
                    .map(name -> name.substring(0, name.length() - ".class".length()))
                    .sorted()
                    .collect(Collectors.toList());
        }
        List<Class<?>> classes = new ArrayList<>();
        for (String name : names) {
            classes.add(Class.forName("controls." + name));
        }
        return classes;
    }
}
