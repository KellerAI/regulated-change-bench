package controls;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** Links a compliance test to the requirement it evidences and says how much of its domain it covers. */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Control {

    String obligation();

    /** Either "exhaustive" or "sample". */
    String coverage();

    String domain();
}
