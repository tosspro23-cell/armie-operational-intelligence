# Sanitized Docker Diagnostics

```text
docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
client=29.8.0 server=29.8.0

docker context show
desktop-linux

docker info --format 'server={{.ServerVersion}} os={{.OperatingSystem}} arch={{.Architecture}} running={{.ContainersRunning}} stopped={{.ContainersStopped}} images={{.Images}} driver={{.Driver}}'
server=29.8.0 os=Docker Desktop arch=aarch64 running=0 stopped=8 images=15 driver=overlayfs

First docker run --rm busybox:latest echo docker-ok:
blocked; no output and disposable container remained Created.

Retry docker run --rm busybox:latest echo docker-ok:
docker-ok

Target after recovery:
Up and healthy; host port 0.0.0.0:18080->8080/tcp.
```

The first healthy target reused a stale experiment network whose container set
was empty, so the host port was unreachable. The Compose network was changed to
the unique `armie-operational-intelligence-spike-live` name and the target was
force-recreated. Host health and checkout then became reachable.

No Docker socket was exposed to the executor. No volume deletion, image
deletion, prune, factory reset, or unrelated container cleanup was performed.
