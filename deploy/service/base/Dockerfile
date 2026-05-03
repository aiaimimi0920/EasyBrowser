# syntax=docker/dockerfile:1.7

FROM golang:1.26-bookworm AS builder
WORKDIR /workspace

COPY service/base ./service/base
WORKDIR /workspace/service/base
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/easybrowser ./cmd/easybrowser

FROM docker:28-cli AS dockercli

FROM debian:bookworm-slim AS runtime
WORKDIR /app

ENV EASYBROWSER_LISTEN=0.0.0.0:18080 \
    EASYBROWSER_RUNTIME_MODE=docker \
    EASYBROWSER_DOCKER_NETWORK=EasyAiMi \
    EASYBROWSER_DOCKER_COMPOSE_PROJECT=easy-browser \
    BROWSER_BINARY_PATH=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    HEADLESS=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /out/easybrowser /usr/local/bin/easybrowser
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY runtimes/chrome /runtimes/chrome
COPY runtimes/chrome/requirements.txt /opt/easybrowser/chrome-runtime-requirements.txt

RUN apt-get -o Acquire::Retries=5 update \
    && sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --fix-missing --no-install-recommends \
        ca-certificates \
        chromium \
        chromium-driver \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcairo2 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libglib2.0-0 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libu2f-udev \
        libx11-6 \
        libx11-xcb1 \
        libxcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        python3 \
        python3-pip \
        xdg-utils \
    && python3 -m pip install --break-system-packages --no-cache-dir --retries 10 --timeout 300 \
        --index-url https://mirrors.aliyun.com/pypi/simple \
        --trusted-host mirrors.aliyun.com \
        -r /opt/easybrowser/chrome-runtime-requirements.txt \
        curl-cffi \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 18080
CMD ["/usr/local/bin/easybrowser"]
