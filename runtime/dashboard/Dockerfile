FROM scratch
# Non-root by default; docker-local.sh passes the invoking user's IDs.
ARG DASHBOARD_UID=65532
ARG DASHBOARD_GID=65532
COPY factory-dashboard /factory-dashboard
ENV HOME=/nonexistent
USER ${DASHBOARD_UID}:${DASHBOARD_GID}
ENTRYPOINT ["/factory-dashboard"]
CMD ["-container","-projects","/inputs/projects.json","-roots-under","/inputs/projects","-feed","/inputs/feed"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s CMD ["/factory-dashboard","-probe"]
