package javax.servlet;

/** Compile-only subset; the real Servlet API is supplied by WebSphere. */
public interface ServletContext {
    String getInitParameter(String name);

    void log(String message);
}
