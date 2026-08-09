<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" session="true" %>
<%
    String node = System.getenv("HOSTNAME");
    if (node == null || node.length() == 0) {
        node = System.getProperty("server.name", "unknown");
    }
    String labName = System.getenv("WAS_LAB_DISPLAY_NAME");
    if (labName == null || labName.length() == 0) {
        labName = "WebSphere ND 9 Cluster Lab";
    }
    Integer visits = (Integer) session.getAttribute("visits");
    visits = visits == null ? Integer.valueOf(1) : Integer.valueOf(visits.intValue() + 1);
    session.setAttribute("visits", visits);
    response.setHeader("X-WAS-Lab-Node", node);
%>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title><%= labName %></title>
  <style>
    body { font-family: sans-serif; max-width: 48rem; margin: 4rem auto; padding: 0 1rem; }
    code { background: #eee; padding: .15rem .35rem; }
  </style>
</head>
<body>
  <h1><%= labName %></h1>
  <p>Request served by container <code><%= node %></code>.</p>
  <p>This HTTP session has recorded <%= visits %> request(s).</p>
</body>
</html>
