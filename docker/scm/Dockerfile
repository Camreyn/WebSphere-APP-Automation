FROM alpine:3.20

# git-daemon changes into the requested bare repository, so its safety check
# observes "." rather than the absolute bind-mount path.
RUN apk add --no-cache git git-daemon \
    && mkdir -p /srv/git \
    && chown -R nobody:nobody /srv/git \
    && git config --system --add safe.directory '*'

USER nobody
EXPOSE 9418

ENTRYPOINT ["git", "daemon", "--reuseaddr", "--base-path=/srv/git", "--export-all", "--verbose", "/srv/git"]
