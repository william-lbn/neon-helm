ARG GO_BUILDER_IMAGE
ARG RUNTIME_IMAGE
FROM ${GO_BUILDER_IMAGE} AS build
WORKDIR /src
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    test -z "$(gofmt -l tools/host-decommission)" && \
    CGO_ENABLED=0 GOMAXPROCS=2 go test -p=2 -count=1 -json -timeout=3m ./tools/host-decommission > /tests.jsonl 2>&1 && \
    CGO_ENABLED=0 GOMAXPROCS=2 go build -p=2 -trimpath -ldflags="-s -w" -o /host-decommission-check ./tools/host-decommission
FROM scratch AS evidence
COPY --from=build /tests.jsonl /tests.jsonl
COPY --from=build /host-decommission-check /host-decommission-check
COPY --from=build /src/source-lock.json /source-lock.json
FROM ${RUNTIME_IMAGE} AS runtime
COPY --from=build --chmod=0555 /host-decommission-check /usr/local/bin/host-decommission-check
ENTRYPOINT ["/usr/local/bin/host-decommission-check"]
