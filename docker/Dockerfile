FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS python
FROM node:22-bookworm-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da
COPY --from=python /usr/local /usr/local
COPY --from=python /usr/lib/x86_64-linux-gnu/libssl.so.3 /usr/lib/x86_64-linux-gnu/
COPY --from=python /usr/lib/x86_64-linux-gnu/libcrypto.so.3 /usr/lib/x86_64-linux-gnu/
COPY --from=python /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
COPY node_modules /opt/pi/node_modules
RUN ln -s /opt/pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js /usr/local/bin/pi
COPY entrypoint.sh /opt/entrypoint.sh
COPY gateway.py /opt/gateway.py
COPY llamacpp_config.py /opt/llamacpp_config.py
USER node
WORKDIR /workspace
ENTRYPOINT ["/bin/sh", "/opt/entrypoint.sh"]
