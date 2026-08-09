FROM nginx:1.27.5-alpine

COPY docker/portal/nginx.conf /etc/nginx/conf.d/default.conf
COPY portal/ /usr/share/nginx/html/

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
