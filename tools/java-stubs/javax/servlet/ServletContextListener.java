package javax.servlet;

import java.util.EventListener;

/** Compile-only subset; the real Servlet API is supplied by WebSphere. */
public interface ServletContextListener extends EventListener {
    void contextInitialized(ServletContextEvent event);

    void contextDestroyed(ServletContextEvent event);
}
