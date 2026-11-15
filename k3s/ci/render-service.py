#!/usr/bin/env python3
"""Render a dormant service registration kit locally; never contacts the server."""
import argparse
import json
import pathlib
import re
from service_config import validate, load_registry


def resources(c, image):
    app = c['name']
    label = {'app.kubernetes.io/name': app}
    meta = lambda name: {'name': name, 'namespace': app}
    container = {'name': 'app', 'image': image, 'imagePullPolicy': 'IfNotPresent',
                 'ports': [{'name': 'http', 'containerPort': c['container_port']}],
                 'envFrom': [{'secretRef': {'name': 'runtime-env'}}],
                 'env': [{'name': 'PORT', 'value': str(c['container_port'])}],
                 'securityContext': {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}},
                 'resources': {'requests': {'cpu': c['resources']['cpu_request'], 'memory': c['resources']['memory_request']},
                               'limits': {'memory': c['resources']['memory_limit']}},
                 'startupProbe': {'httpGet': {'path': c['health_path'], 'port': 'http'}, 'periodSeconds': 5, 'timeoutSeconds': 2, 'failureThreshold': 24},
                 'readinessProbe': {'httpGet': {'path': c['health_path'], 'port': 'http'}, 'periodSeconds': 5, 'timeoutSeconds': 2},
                 'livenessProbe': {'tcpSocket': {'port': 'http'}, 'periodSeconds': 20, 'timeoutSeconds': 2}}
    items = [{'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': app}},
             {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': meta(app),
              'spec': {'replicas': 0, 'revisionHistoryLimit': 2, 'progressDeadlineSeconds': 180,
                       'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': label},
                       'template': {'metadata': {'labels': label}, 'spec': {
                           'automountServiceAccountToken': False, 'terminationGracePeriodSeconds': 30,
                           'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}}, 'containers': [container]}}}},
             {'apiVersion': 'v1', 'kind': 'Service', 'metadata': meta(app),
              'spec': {'type': 'NodePort', 'selector': label, 'ports': [{'name': 'http', 'port': c['container_port'], 'targetPort': 'http', 'nodePort': c['node_port']}]}}]
    if c['database']:
        items += [{'apiVersion': 'v1', 'kind': 'Service', 'metadata': meta('postgres'),
                   'spec': {'ports': [{'name': 'postgres', 'port': 5432, 'targetPort': 5432}]}},
                  {'apiVersion': 'discovery.k8s.io/v1', 'kind': 'EndpointSlice',
                   'metadata': {**meta('postgres-host'), 'labels': {'kubernetes.io/service-name': 'postgres', 'endpointslice.kubernetes.io/managed-by': 'lightsail-infra'}},
                   'addressType': 'IPv4', 'ports': [{'name': 'postgres', 'protocol': 'TCP', 'port': 5432}],
                   'endpoints': [{'addresses': [c['database']['host_ip']], 'conditions': {'ready': True}}]}]
    return {'apiVersion': 'v1', 'kind': 'List', 'items': items}


def caller(c, ref, dockerfile, context, check):
    branch = c['production_branch']
    # JSON-quoted YAML scalars preserve caller-provided command/path text literally.
    q = json.dumps
    template = '''name: CI/CD (k3s)
on:
  push:
    branches: [BRANCH]
  pull_request:
    branches: [BRANCH]
  workflow_dispatch:
    inputs:
      publish_only:
        description: Publish an image without deploying (for first bootstrap).
        type: boolean
        default: false
permissions:
  contents: read
concurrency:
  group: k3s-${{ github.ref }}
  cancel-in-progress: false
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # Add the runtime setup (Node/Python/Go/etc.) required by your application.
      - name: Test and build application
        run: CHECK
  release:
    needs: validate
    if: github.ref == 'refs/heads/BRANCH_RAW' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')
    uses: no-ikjun/lightsail-infra/.github/workflows/k3s-release.yml@REF
    with:
      service: SERVICE
      production_branch: BRANCH
      image_repository: IMAGE
      dockerfile: DOCKERFILE
      build_context: CONTEXT
      # Until bootstrap is verified, pushes publish only. Set the repository variable to true afterward.
      deploy: ${{ vars.K3S_DEPLOY_ENABLED == 'true' && inputs.publish_only != true }}
    secrets:
      DOCKER_USERNAME: ${{ secrets.DOCKER_USERNAME }}
      DOCKER_PASSWORD: ${{ secrets.DOCKER_PASSWORD }}
      LIGHTSAIL_HOST: ${{ secrets.LIGHTSAIL_HOST }}
      LIGHTSAIL_USERNAME: ${{ secrets.LIGHTSAIL_USERNAME }}
      LIGHTSAIL_SSH_KEY: ${{ secrets.LIGHTSAIL_SSH_KEY }}
      LIGHTSAIL_KNOWN_HOSTS: ${{ secrets.LIGHTSAIL_KNOWN_HOSTS }}
      SSH_PORT: ${{ secrets.SSH_PORT }}
'''
    values = {'BRANCH_RAW': branch, 'BRANCH': q(branch), 'CHECK': q(check),
              'REF': ref, 'SERVICE': q(c['name']), 'IMAGE': q(c['image_repository']),
              'DOCKERFILE': q(dockerfile), 'CONTEXT': q(context)}
    return re.sub(r'\b(BRANCH_RAW|BRANCH|CHECK|REF|SERVICE|IMAGE|DOCKERFILE|CONTEXT)\b',
                  lambda m: values[m.group()], template)



def render(config_path, output, ref, check, image=None, dockerfile='Dockerfile', context='.', registry=None):
    c = validate(json.loads(pathlib.Path(config_path).read_text()))
    if not re.fullmatch(r'[a-f0-9]{40}', ref):
        raise ValueError('Pin the reusable workflow to a reviewed full commit SHA')
    if not check.strip():
        raise ValueError('Provide the application test/build command')
    existing = load_registry() if registry is None else registry
    for name, other in existing.items():
        if name != c['name'] and (other['node_port'] == c['node_port'] or other['hostname'] == c['hostname']):
            raise ValueError('NodePort/hostname already registered: ' + name)
    if image is not None and not re.fullmatch(re.escape(c['image_repository']) + r'@sha256:[a-f0-9]{64}', image):
        raise ValueError('Bootstrap image must match the registered repository and digest')
    image = image or c['image_repository'] + ':BOOTSTRAP_REQUIRED'
    output = pathlib.Path(output)
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite a reviewed kit or secrets.
    (output / 'service.json').write_text(json.dumps(c, indent=2) + '\n')
    (output / 'resources.json').write_text(json.dumps(resources(c, image), indent=2) + '\n')
    (output / 'deploy.yml').write_text(caller(c, ref, dockerfile, context, check))
    (output / 'runtime.env.example').write_text('# Variable names only. Keep real values OUT of Git.\n# APP_SETTING=replace-locally\n# For multiline secrets, use a JSON Secret/from-file; do not flatten keys into env-file.\n')
    (output / 'nginx-http.conf').write_text('''# Bootstrap HTTP vhost. Obtain TLS with certbot --nginx after DNS is verified.
server {
    listen 80;
    listen [::]:80;
    server_name HOSTNAME;
    if (-f /run/SERVICE-maintenance.flag) { return 503; }
    location / {
        proxy_pass http://127.0.0.1:NODEPORT;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
'''.replace('HOSTNAME', c['hostname']).replace('SERVICE', c['name']).replace('NODEPORT', str(c['node_port'])))
    (output / 'README.md').write_text('''# Initial registration kit

This kit is dormant: replicas=0 and K3S_DEPLOY_ENABLED is false until explicitly enabled. It does not create a database, credentials, DNS records or certificates. Follow k3s/templates/service/README.md in lightsail-infra.

After reviewing this kit: register service.json on the host; apply resources.json; create runtime-env privately; provision DB/permissions if configured; install the nginx vhost and HTTPS; publish the first image using the workflow (publish-only); set the verified image digest while replicas=0; scale to 1 and validate health/data/memory; then set repository variable K3S_DEPLOY_ENABLED=true.

Do not re-apply this initial replicas=0 manifest over a running service. Promote a reviewed replicas=1 snapshot with the current digest for ongoing infrastructure management. Application code updates use Actions.
''')
    return output


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('config')
    p.add_argument('--output', required=True)
    p.add_argument('--workflow-ref', required=True)
    p.add_argument('--check-command', required=True)
    p.add_argument('--image')
    p.add_argument('--dockerfile', default='Dockerfile')
    p.add_argument('--build-context', default='.')
    a = p.parse_args()
    print(render(a.config, a.output, a.workflow_ref, a.check_command, a.image, a.dockerfile, a.build_context))
