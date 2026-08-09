<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" session="true" %>
<%
    String applicationName = application.getInitParameter("waslab.applicationName");
    String description = application.getInitParameter("waslab.description");
    String accentColor = application.getInitParameter("waslab.accentColor");
    String node = System.getenv("HOSTNAME");
    if (node == null || node.length() == 0) {
        node = System.getProperty("server.name", "unknown");
    }
    Integer visits = (Integer) session.getAttribute("visits");
    visits = visits == null ? Integer.valueOf(1) : Integer.valueOf(visits.intValue() + 1);
    session.setAttribute("visits", visits);
    response.setHeader("X-WAS-Lab-Application", applicationName);
    response.setHeader("X-WAS-Lab-Node", node);
%>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><%= applicationName %></title>
  <style>
    :root { --accent: <%= accentColor %>; color-scheme: light; }
    body { background: #f8fafc; color: #172033; font-family: system-ui, sans-serif; margin: 0; }
    main { background: white; border-top: .45rem solid var(--accent); border-radius: .6rem;
           box-shadow: 0 .6rem 2rem rgba(15, 23, 42, .12); margin: 4rem auto;
           max-width: 48rem; padding: 2rem; }
    h1 { color: var(--accent); margin-top: 0; }
    dl { display: grid; grid-template-columns: 10rem 1fr; gap: .7rem 1rem; }
    dt { font-weight: 700; }
    code { background: #eef2f7; border-radius: .25rem; padding: .15rem .4rem; }
  </style>
</head>
<body>
  <main>
    <h1><%= applicationName %></h1>
    <p><%= description %></p>
    <dl>
      <dt>Packaging</dt><dd>Java EE EAR containing one WAR module</dd>
      <dt>Context root</dt><dd><code><%= request.getContextPath() %></code></dd>
      <dt>WebSphere host</dt><dd><code><%= node %></code></dd>
      <dt>Session visits</dt><dd><%= visits %></dd>
      <dt>Server time</dt><dd><%= new java.util.Date() %></dd>
    </dl>
  </main>
</body>
</html>
