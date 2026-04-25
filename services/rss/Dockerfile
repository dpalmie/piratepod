FROM golang:1.25-alpine AS build
WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .

# CGO_ENABLED=0 because modernc.org/sqlite is pure Go.
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/rss ./cmd/rss

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/rss /rss

ENV PIRATEPOD_MODE=self_host \
    PIRATEPOD_PORT=8080 \
    PIRATEPOD_SQLITE_PATH=/data/piratepod.db \
    PIRATEPOD_MEDIA_DIR=/data/media

EXPOSE 8080
VOLUME ["/data"]
USER nonroot:nonroot
ENTRYPOINT ["/rss"]
