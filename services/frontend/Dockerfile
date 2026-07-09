FROM nginx:1.27-alpine
COPY services/frontend/index.html /usr/share/nginx/html/index.html
COPY services/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY services/frontend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s CMD wget -qO- http://localhost:80 || exit 1
ENTRYPOINT ["/docker-entrypoint.sh"]
