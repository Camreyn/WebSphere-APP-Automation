package javax.servlet;

import java.util.EventObject;

/** Compile-only subset; this class is never packaged in the sample WAR. */
public class ServletContextEvent extends EventObject {
    public ServletContextEvent(ServletContext source) {
        super(source);
    }

    public ServletContext getServletContext() {
        return (ServletContext) getSource();
    }
}
