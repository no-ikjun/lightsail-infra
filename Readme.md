# lightsail-infra

AWS Lightsail의 단일 노드 **k3s**에서 arrive와 sprit을 운영하기 위한 공통 배포 workflow와 새 서비스 등록 템플릿입니다. 앱 저장소의 GitHub Actions가 테스트·빌드 후 Docker Hub에 이미지를 게시하고, SSH로 호스트 배포기를 호출해 Kubernetes Deployment를 갱신합니다.

이 공개 저장소에는 재사용 가능한 workflow·설정 검증기·생성기를 제공합니다. 서버별 등록 정보, 호스트 배포 도구와 상세 운영 기록은 별도로 관리하므로, 이 저장소를 clone하는 것만으로 운영 서버가 설치되지는 않습니다.

## 현재 구성

| 역할 | 구성 |
|---|---|
| 외부 요청·HTTPS | 호스트 Nginx와 Certbot |
| 애플리케이션 실행 | 단일 노드 k3s, 서비스별 Deployment와 Pod 1개 |
| 배포 전략 | `Recreate`: 기존 Pod 종료 후 새 Pod 기동 |
| 데이터베이스 | 호스트 Docker의 공유 PostgreSQL, 서비스별 DB·권한 분리 |
| CI | GitHub-hosted runner에서 앱별 테스트와 빌드 |
| 이미지 저장소 | Docker Hub, 배포 시 immutable `image@sha256:…` 사용 |
| CD | GitHub Actions 재사용 workflow → SSH → 호스트 공통 배포기 |
| 런타임 설정 | Kubernetes Secret, 배포 접속 정보는 GitHub Actions Secrets |

Argo CD는 설치하지 않았습니다. 현재 앱 배포는 GitHub Actions가 담당하며, 지속적인 GitOps 동기화 컨트롤러는 사용하지 않습니다. `Recreate` 배포에는 짧은 서비스 중단이 발생할 수 있습니다.

기존 `compose/`의 Traefik·Docker Compose 구성은 과거 구성입니다. 현재 앱 운영은 위의 k3s·Nginx 구성을 따릅니다. 과거 Compose 기동 명령을 현재 서버의 설치·배포 절차로 사용하지 않습니다.

## 기존 서비스 배포

| 서비스 | 자동 배포 | 수동 배포 |
|---|---|---|
| arrive | `main`의 backend·지정된 contracts·배포 관련 파일 변경 push | **CI/CD (k3s) → Run workflow → main** |
| sprit | `production` push | **CI/CD (k3s) → Run workflow → production** |

PR에서는 앱 검증만 수행합니다. 정확한 경로 필터와 앱별 검증 단계는 [arrive workflow](https://github.com/no-ikjun/arrive/blob/main/.github/workflows/deploy.yml), [sprit workflow](https://github.com/no-ikjun/sprit-be/blob/production/.github/workflows/deploy.yml)를 기준으로 합니다. 두 서비스의 자동·수동 배포는 2026-11-15에 검증했고, 이 문서의 workflow 설명은 2026-11-18에 다시 대조했습니다.

공통 배포 흐름은 다음과 같습니다.

1. 앱 저장소에서 테스트·빌드 및 앱별 호환성 검사를 수행합니다.
2. [공통 release workflow](.github/workflows/k3s-release.yml)가 `linux/amd64` 이미지를 빌드해 Docker Hub에 게시합니다.
3. 검증된 SSH 호스트 키로 접속해 이미지 digest와 소스 커밋을 호스트 배포기에 전달합니다.
4. 호스트는 서비스 등록 정보·이미지 출처·기존 서비스 상태를 확인하고, 설정된 사전 검사와 PostgreSQL 백업을 수행합니다.
5. Pod 교체 후 Ready 상태와 HTTP/HTTPS 응답을 확인합니다. 교체 실패 시 같은 DB를 유지하면서 이전 Pod template으로 복구를 시도합니다.

서비스 간 배포는 호스트의 공통 잠금으로 직렬화합니다. DB 백업은 서버에만 보관하며, 이미지 복구가 DB 스키마 변경을 되돌리지는 않습니다. 스키마 변경은 별도 마이그레이션 절차가 필요합니다.

## 재사용 workflow

각 앱 저장소는 테스트·트리거·배포 브랜치를 관리하고, 검증 job 이후 공통 workflow를 호출합니다. 현재 기존 서비스가 사용하는 고정 참조는 다음과 같습니다.

```yaml
uses: no-ikjun/lightsail-infra/.github/workflows/k3s-release.yml@6ca6b41f5d1c970f8c7fe45098ff70071968ff72
```

주요 입력은 `service`, `image_repository`, `production_branch`, `dockerfile`, `build_context`입니다. `deploy: false`는 이미지만 게시하고 서버 배포를 건너뜁니다. 기본값은 `true`이며, 새 서비스용 생성 workflow는 별도 활성화 변수를 확인합니다. job 간에는 digest만 전달하고, 다음 job에서 이미지 저장소와 조합합니다.

필요한 repository Actions Secrets는 다음과 같습니다. 실제 값은 Git에 저장하지 않습니다.

| Secret | 용도 |
|---|---|
| `DOCKER_USERNAME`, `DOCKER_PASSWORD` | Docker Hub 이미지 push 인증 |
| `LIGHTSAIL_HOST`, `LIGHTSAIL_USERNAME` | 배포 서버와 SSH 계정 |
| `LIGHTSAIL_SSH_KEY` | 배포용 SSH 개인키 |
| `LIGHTSAIL_KNOWN_HOSTS` | 독립적으로 검증한 서버 호스트 키 |
| `SSH_PORT` | 선택 사항, 기본 22 |

전체 입력·호스트 키 형식·호출 조건은 [workflow 사용 안내](.github/workflows/README.md)를 참고합니다. 공통 workflow는 커밋 SHA로 고정하므로, 공통 변경을 게시한 뒤 각 앱의 참조 SHA를 갱신해야 적용됩니다.

## 새 서비스 추가

### 1. 설정 작성과 파일 생성

[서비스 설정 예제](k3s/templates/service/service.json)를 복사해 서비스명, 앱 저장소, 배포 브랜치, 이미지 저장소, 도메인, 포트, 리소스 예산을 수정합니다. DB를 사용하지 않으면 `database: null`을 유지합니다. 실제 DB 주소 등 서버별 설정은 공개 커밋에 포함하지 않습니다.

```sh
mkdir -p k3s/.local
cp k3s/templates/service/service.json k3s/.local/new-service.json
# new-service.json을 새 서비스에 맞게 수정한 다음 실행
python3 k3s/ci/render-service.py k3s/.local/new-service.json \
  --output k3s/.local/new-service-kit \
  --workflow-ref 6ca6b41f5d1c970f8c7fe45098ff70071968ff72 \
  --check-command 'npm ci --no-audit --no-fund && npm test && npm run build'
```

생성기는 Python 3 표준 라이브러리로 실행합니다. 예시의 검증 명령은 앱에 맞게 바꾸고, 생성된 workflow에 필요한 Node/Python/Go 등의 런타임 준비 단계를 추가합니다. Dockerfile 위치와 빌드 컨텍스트가 다르면 `--dockerfile`, `--build-context`를 지정합니다. 기존 출력 폴더는 덮어쓰지 않습니다.

결과물은 서비스 등록 JSON, Kubernetes 리소스, 앱 저장소용 `deploy.yml`, Nginx HTTP 설정과 환경변수 예제입니다. Kubernetes 리소스는 **replicas=0**으로 생성되며, 초기 이미지 자리표시자는 실제 배포 이미지로 교체해야 합니다. 공개 checkout에는 운영 서비스 목록이 없으므로 포트·도메인 충돌은 운영 등록 정보와도 대조해야 합니다.

### 2. 최초 기동과 자동 배포 활성화

1. 앱 저장소에 Dockerfile과 생성된 `.github/workflows/deploy.yml`을 추가하고 Actions Secrets를 설정합니다. 수동 버튼을 사용하려면 기본 브랜치에도 workflow가 있어야 합니다.
2. 호스트 운영 절차로 서비스를 등록하고 runtime Secret, 필요한 DB·계정·권한, DNS와 HTTPS를 준비합니다. 서버의 여유 자원과 앱의 실제 메모리 사용량도 확인합니다.
3. `K3S_DEPLOY_ENABLED`를 아직 설정하지 않은 상태에서 배포 브랜치 push 또는 수동 실행으로 최초 이미지를 게시합니다. 생성된 workflow는 이 단계에서 서버 배포를 건너뜁니다.
4. 게시된 digest를 초기 Deployment에 지정하고 Pod 1개로 기동한 뒤 health·인증·데이터 보존과 기존 서비스 영향을 확인합니다.
5. 검증 후 앱 저장소의 Actions **Variables**에 `K3S_DEPLOY_ENABLED=true`를 설정합니다. 이후 배포 브랜치 push 또는 **Run workflow**로 배포합니다. `publish_only=true`를 선택하면 이미지 게시만 수행합니다.

초기 `replicas=0` manifest를 운영 중인 서비스에 그대로 재적용하지 않습니다. 운영용 manifest는 현재 digest와 replicas를 반영해 별도 관리합니다. 생성기는 호스트 배포 도구 설치, DB 생성, Secret 주입, DNS·인증서 설정을 자동으로 수행하지 않습니다.

## 공개 범위

이 README와 공개 코드에는 실제 서버 주소·내부 네트워크/DB 주소·호스트 키 값·계정 비밀번호·개인키·백업 위치 및 내용을 포함하지 않습니다. 상세 운영 문서와 호스트 배포 도구는 운영자가 별도로 보관합니다. `k3s/.local/`은 Git에서 제외된 작업 공간이며, 실제 비밀값을 다른 추적 파일에 복사하지 않습니다.
