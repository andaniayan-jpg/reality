FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html styles.css app.js hero3d.bundle.js hero-reference.js hero-physics.js runtime-config.js /usr/share/nginx/html/
COPY assets/ /usr/share/nginx/html/assets/
COPY THIRD_PARTY_NOTICES.md /usr/share/nginx/html/
COPY 10-api-base.sh /docker-entrypoint.d/10-api-base.sh
