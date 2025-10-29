# lightsail-infra

AWS Lightsail 위에서 **여러 백엔드 서비스**(Docker 컨테이너)를 **Traefik 리버스 프록시**로 라우팅하고,  
각 서비스 레포의 GitHub Actions에서 **이미지 빌드 → GHCR 푸시 → Lightsail SSH 배포(부분 재시작)** 하는 구조.

또한 `argocd/` 폴더에는 **k3s + ArgoCD** 학습/모니터링용 매니페스트를 포함(선택 적용).

## 구성 개요

- Reverse Proxy / TLS: **Traefik v3**
- 컨테이너 오케스트레이션(경량): **Docker Compose**
- CI: 각 서비스 레포에서 **GitHub Actions** (docker build & push)
- CD: 각 서비스 레포에서 **Appleboy SSH Action**으로 이 레포의 compose를 원격 실행
- Observability(학습/선택): **k3s + ArgoCD** (상태/헬스/롤백)

## 도메인 예시 (수정하세요)

- Sprit API: `api.sprit.ikjun.com` → `sprit-api` 컨테이너(포트 3000)
- Analyst API: `analyst.ikjun.com` → `analyst-api` 컨테이너(포트 8000)

## 서버 최초 세팅

```bash
# 연결
ssh ubuntu@YOUR_LIGHTSAIL_IP

# 기본 패키지 & Docker
sudo apt update && sudo apt -y upgrade
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version

# 방화벽 (필요시)
sudo apt -y install ufw
sudo ufw allow 22 && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable

# 레포 배치
git clone https://github.com/no-ikjun/lightsail-infra.git
cd lightsail-infra/compose
mkdir -p traefik/acme && touch traefik/acme/acme.json && chmod 600 traefik/acme/acme.json

# 환경 변수 템플릿 복사
cp .env.example .env
# <-- .env 내용 값을 실제로 채우세요

# 기동
docker compose pull
docker compose up -d
docker compose ps
```
