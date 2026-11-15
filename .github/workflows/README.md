# Reusable k3s release

Call `no-ikjun/lightsail-infra/.github/workflows/k3s-release.yml` at a reviewed full commit SHA from an application repository after its validation job. Keep push/PR/manual triggers and `concurrency: cancel-in-progress: false` in the caller. PRs must not call the release job. Supply the service name, Docker Hub image repository, production branch, Dockerfile and build context.

The workflow builds on a GitHub-hosted runner, publishes an immutable image and invokes the host-installed deployment helper over SSH. The host must already have a registered, healthy service and runtime credentials. `deploy: false` publishes an image without changing the host, for first bootstrap. The workflow does not install Kubernetes or provision a service.

Required repository secrets: `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `LIGHTSAIL_HOST`, `LIGHTSAIL_USERNAME`, `LIGHTSAIL_SSH_KEY`, `LIGHTSAIL_KNOWN_HOSTS`. Optional: `SSH_PORT` (22). Known hosts must contain an independently verified key with alias `lightsail-production`; do not trust a key discovered during deployment.

Generic service configuration starts at `k3s/templates/service/service.json`. Run `python3 k3s/ci/render-service.py CONFIG --output NEW_DIRECTORY --workflow-ref REVIEWED_FULL_SHA --check-command 'YOUR_TEST_AND_BUILD_COMMAND'` to generate a dormant manifest, caller workflow, nginx HTTP config and environment-variable example. Add runtime setup to the generated validation job. Provision the host registration, runtime Secret, optional database, DNS and HTTPS separately. The first manifest has zero replicas; select a verified image digest and validate initial startup before enabling repository variable `K3S_DEPLOY_ENABLED=true`.

Production inventories, host keys, database credentials, backup contents and deployment evidence are deliberately not part of this generic public package. The host deployment tools and detailed operational guide are maintained in the operator's protected infrastructure checkout. Updating the shared workflow does not change SHA-pinned callers until their pin is explicitly updated.
