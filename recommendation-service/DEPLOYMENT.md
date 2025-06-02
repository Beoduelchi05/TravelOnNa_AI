# 🚀 TravelOnNa AI 추천 서비스 배포 가이드

## 📋 배포 아키텍처

```
GitHub → Jenkins (EC2-1) → Docker Buildx → Kubernetes (EC2-2/3)
```

기존 Spring Boot 서버와 동일한 CI/CD 파이프라인을 사용하며, Docker Buildx로 멀티플랫폼 빌드를 지원합니다.

## 🔧 배포 준비사항

### 1. Jenkins 설정 (EC2-1)

```bash
# Python 3.11 설치 (Jenkins 서버에)
sudo apt update
sudo apt install -y python3.11 python3.11-pip python3.11-venv

# Docker Buildx 설정
docker buildx version
docker buildx create --name travelonna-builder --use --bootstrap
docker buildx ls

# Docker 권한 확인
sudo usermod -aG docker jenkins
sudo systemctl restart jenkins
```

### 2. Docker Buildx 환경 준비

```bash
# BuildKit 활성화
export DOCKER_BUILDKIT=1

# Multi-platform 빌드를 위한 QEMU 설정 (필요시)
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Builder 인스턴스 확인
docker buildx inspect --bootstrap
```

### 3. Kubernetes 클러스터 준비 (EC2-2/3)

```bash
# kubectl 명령어가 Jenkins에서 작동하는지 확인
kubectl cluster-info
kubectl get nodes
```

### 4. 데이터베이스 연결 설정

`k8s/configmap.yaml`에서 실제 DB 정보로 수정:

```yaml
data:
  db.host: "your-mysql-rds-endpoint"  # RDS 엔드포인트
  db.name: "travelonna_production"    # 실제 DB명
```

`k8s/configmap.yaml`에서 Secret 생성:

```bash
# Base64 인코딩
echo -n "your-db-username" | base64
echo -n "your-db-password" | base64
```

## 🚀 배포 단계

### Step 1: 코드 Push
```bash
git add .
git commit -m "feat: AI 추천 서비스 배포 준비 (Buildx)"
git push origin main
```

### Step 2: Jenkins 파이프라인 생성

1. Jenkins 대시보드 접속
2. "New Item" → "Pipeline" 선택
3. Pipeline 이름: `travelonna-ai-recommendation`
4. Pipeline script from SCM 선택
5. Repository URL과 Jenkinsfile 경로 설정

### Step 3: 로컬에서 Buildx 테스트 (선택사항)

```bash
cd TravelOnNa_AI/recommendation-service

# 단일 플랫폼 빌드 (빠른 테스트)
docker buildx build --platform linux/amd64 -t travelonna-ai-recommendation:test .

# 멀티 플랫폼 빌드 (프로덕션)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag travelonna-ai-recommendation:latest \
  --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
  --build-arg VCS_REF=$(git rev-parse --short HEAD) \
  --build-arg BUILD_NUMBER=local \
  --cache-from type=local,src=/tmp/.buildx-cache \
  --cache-to type=local,dest=/tmp/.buildx-cache-new,mode=max \
  --load \
  .
```

### Step 4: 수동 배포 (첫 번째)

```bash
# EC2-1 (Jenkins 서버)에서 실행

# 1. Buildx 이미지 빌드
cd /path/to/TravelOnNa_AI/recommendation-service
docker buildx build --platform linux/amd64,linux/arm64 -t travelonna-ai-recommendation:v1 --load .

# 2. ConfigMap과 Secret 생성
kubectl apply -f k8s/configmap.yaml

# 3. 배포
kubectl apply -f k8s/deployment.yaml

# 4. 상태 확인
kubectl get pods -l app=travelonna-ai-recommendation
kubectl get svc travelonna-ai-recommendation-service
```

### Step 5: 배포 검증

```bash
# 서비스 엔드포인트 확인
kubectl get svc travelonna-ai-recommendation-service

# 헬스체크
SERVICE_IP=$(kubectl get svc travelonna-ai-recommendation-service -o jsonpath='{.spec.clusterIP}')
curl http://${SERVICE_IP}:8000/health

# 이미지 정보 확인
kubectl get pods -l app=travelonna-ai-recommendation -o jsonpath='{.items[0].spec.containers[0].image}'

# 로그 확인
kubectl logs -l app=travelonna-ai-recommendation --tail=100
```

## 🔄 CI/CD 플로우

### 자동 배포 트리거
- `main` 브랜치에 Push 시 자동 배포
- Jenkins에서 다음 단계 실행:
  1. 코드 체크아웃
  2. Docker Buildx 설정
  3. Python 테스트 및 문법 검사
  4. Docker Buildx 멀티플랫폼 빌드
  5. 이미지 보안 스캔 (선택)
  6. Kubernetes 배포
  7. 헬스체크

### 수동 배포
```bash
# Jenkins에서 수동 빌드 실행
curl -X POST http://jenkins-server:8080/job/travelonna-ai-recommendation/build \
  --user your-jenkins-user:your-api-token
```

## 🐳 Docker Buildx 고급 기능

### 캐시 최적화
```bash
# 레지스트리 캐시 사용 (권장)
docker buildx build \
  --cache-from type=registry,ref=myregistry/myapp:buildcache \
  --cache-to type=registry,ref=myregistry/myapp:buildcache,mode=max \
  .

# 로컬 캐시 사용
docker buildx build \
  --cache-from type=local,src=/tmp/.buildx-cache \
  --cache-to type=local,dest=/tmp/.buildx-cache-new,mode=max \
  .
```

### 멀티플랫폼 빌드
```bash
# ARM64 Mac과 AMD64 서버 호환
docker buildx build --platform linux/amd64,linux/arm64 .

# 특정 플랫폼만
docker buildx build --platform linux/amd64 .
```

### 빌드 정보 확인
```bash
# 빌드 히스토리
docker buildx ls

# 상세 정보
docker buildx inspect travelonna-builder

# 캐시 정보
docker buildx du
```

## 🏗️ 인프라 구성

```
┌─────────────────────────────────────────────────────────────┐
│                        EC2-1 (Jenkins)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Jenkins   │  │Docker Buildx│  │      Ansible        │ │
│  │   Server    │  │Multi-Platform│  │   (if needed)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     EC2-2 (K8s Master)                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Kubernetes Control Plane                  │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │ │
│  │  │    etcd     │  │ API Server  │  │   Scheduler     │ │ │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     EC2-3 (K8s Worker)                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    Workloads                            │ │
│  │  ┌─────────────┐  ┌─────────────────────────────────────┐ │ │
│  │  │   Spring    │  │    FastAPI (Multi-Platform!)       │ │ │
│  │  │   Backend   │  │   ┌─────────────────────────────┐ │ │ │
│  │  │   Pods      │  │   │  Recommendation Service   │ │ │ │
│  │  │             │  │   │  (Python/FastAPI/Buildx)  │ │ │ │
│  │  └─────────────┘  │   └─────────────────────────────┘ │ │
│  │                   └─────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 모니터링 및 유지보수

### 로그 확인
```bash
# 전체 로그
kubectl logs -l app=travelonna-ai-recommendation

# 실시간 로그
kubectl logs -l app=travelonna-ai-recommendation -f

# 특정 Pod 로그
kubectl logs pod-name
```

### 이미지 및 캐시 관리
```bash
# Buildx 캐시 확인
docker buildx du

# 캐시 정리
docker buildx prune

# 이미지 정보 확인
docker buildx imagetools inspect travelonna-ai-recommendation:latest
```

### 리소스 모니터링
```bash
# Pod 상태
kubectl get pods -l app=travelonna-ai-recommendation

# 리소스 사용량
kubectl top pods -l app=travelonna-ai-recommendation

# 서비스 상태
kubectl get svc travelonna-ai-recommendation-service
```

### 스케일링
```bash
# 수평 확장
kubectl scale deployment travelonna-ai-recommendation --replicas=3

# 자동 스케일링 (HPA) 설정
kubectl autoscale deployment travelonna-ai-recommendation \
  --cpu-percent=70 --min=2 --max=10
```

## 🚨 트러블슈팅

### 일반적인 문제들

1. **Buildx 관련 오류**
   ```bash
   # Builder 재생성
   docker buildx rm travelonna-builder
   docker buildx create --name travelonna-builder --use --bootstrap
   
   # QEMU 재설정 (멀티플랫폼 빌드시)
   docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
   ```

2. **이미지 Pull 오류**
   ```bash
   kubectl describe pod <pod-name>
   # ImagePullBackOff 확인 시 → 이미지 태그 및 플랫폼 확인
   ```

3. **데이터베이스 연결 실패**
   ```bash
   kubectl logs <pod-name>
   # DB 연결 정보 확인
   kubectl get configmap app-config -o yaml
   kubectl get secret db-secret -o yaml
   ```

4. **헬스체크 실패**
   ```bash
   kubectl describe deployment travelonna-ai-recommendation
   # readinessProbe, livenessProbe 상태 확인
   ```

## 📊 성능 최적화

### Buildx 캐시 전략
- **로컬 캐시**: 빠른 개발용
- **레지스트리 캐시**: 팀 공유용
- **인라인 캐시**: CI/CD 최적화

### 멀티스테이지 빌드 최적화
- 의존성 설치와 애플리케이션 복사 분리
- 불필요한 파일 제거
- 보안 강화 (non-root 사용자)

## 📞 연락처

- DevOps 담당: [담당자]
- AI 서비스 담당: [담당자] 