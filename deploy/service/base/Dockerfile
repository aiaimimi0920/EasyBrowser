# syntax=docker/dockerfile:1.7

FROM golang:1.26-bookworm AS builder
WORKDIR /workspace

COPY service/base ./service/base
WORKDIR /workspace/service/base
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/easybrowser ./cmd/easybrowser

FROM debian:bookworm-slim AS runtime
WORKDIR /app

ENV EASYBROWSER_LISTEN=0.0.0.0:18080

COPY --from=builder /out/easybrowser /usr/local/bin/easybrowser

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 18080
CMD ["/usr/local/bin/easybrowser"]
