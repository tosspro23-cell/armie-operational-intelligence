# Sanitized Docker Diagnostics

Commands were run read-only except for the exact disposable busybox smoke-test
container cleanup after it failed to auto-remove.

```text
docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
client=29.8.0 server=29.8.0

docker context show
desktop-linux

docker info --format 'server={{.ServerVersion}} os={{.OperatingSystem}} arch={{.Architecture}} running={{.ContainersRunning}} stopped={{.ContainersStopped}} images={{.Images}} driver={{.Driver}}'
server=29.8.0 os=Docker Desktop arch=aarch64 running=0 stopped=8 images=15 driver=overlayfs

docker run --rm busybox:latest echo docker-ok
No output; bounded command did not complete. The disposable container was observed in Created state.

docker compose up -d --build target
Image built successfully; target container remained Created after the bounded start wait.

Sanitized target state:
status=created running=false started=0001-01-01T00:00:00Z exit=0 oom=false error=
```

No Docker socket, volume deletion, image deletion, prune, factory reset, or
unrelated container cleanup was performed.
