package com.waslab;

import javax.servlet.ServletContext;
import javax.servlet.ServletContextEvent;
import javax.servlet.ServletContextListener;

/** Adds a visible, bounded startup window for the WebSphere automation lab. */
public final class StartupDelayListener implements ServletContextListener {
    private static final String PARAMETER_NAME = "waslab.startupDelaySeconds";
    private static final long DEFAULT_DELAY_SECONDS = 10L;
    private static final long MAXIMUM_DELAY_SECONDS = 300L;

    @Override
    public void contextInitialized(ServletContextEvent event) {
        ServletContext context = event.getServletContext();
        long delaySeconds = readDelaySeconds(context);
        long started = System.nanoTime();
        context.log("WASLAB_STARTUP_DELAY_BEGIN seconds=" + delaySeconds);
        try {
            Thread.sleep(delaySeconds * 1000L);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            context.log("WASLAB_STARTUP_DELAY_INTERRUPTED");
        }
        long elapsedMillis = (System.nanoTime() - started) / 1000000L;
        context.log("WASLAB_STARTUP_DELAY_COMPLETE elapsedMillis=" + elapsedMillis);
    }

    @Override
    public void contextDestroyed(ServletContextEvent event) {
        // No resources are retained after startup.
    }

    private static long readDelaySeconds(ServletContext context) {
        String configured = context.getInitParameter(PARAMETER_NAME);
        if (configured == null || configured.trim().length() == 0) {
            return DEFAULT_DELAY_SECONDS;
        }
        try {
            long seconds = Long.parseLong(configured.trim());
            if (seconds < 0L || seconds > MAXIMUM_DELAY_SECONDS) {
                throw new NumberFormatException("outside supported range");
            }
            return seconds;
        } catch (NumberFormatException exception) {
            context.log(
                "WASLAB_STARTUP_DELAY_INVALID value=" + configured
                    + " defaultSeconds=" + DEFAULT_DELAY_SECONDS
            );
            return DEFAULT_DELAY_SECONDS;
        }
    }
}
