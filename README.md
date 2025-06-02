# 🌟 TravelOnNa AI 추천시스템

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-green.svg)
![Machine Learning](https://img.shields.io/badge/ML-ALS%20Algorithm-orange.svg)
![Docker](https://img.shields.io/badge/docker-enabled-blue.svg)
![Kubernetes](https://img.shields.io/badge/kubernetes-ready-green.svg)

**여행ON나 플랫폼의 AI 기반 개인화 추천 시스템**

## 📋 목차
- [프로젝트 개요](#-프로젝트-개요)
- [시스템 아키텍처](#-시스템-아키텍처)
- [주요 기능](#-주요-기능)
- [기술 스택](#-기술-스택)
- [디렉토리 구조](#-디렉토리-구조)
- [빠른 시작](#-빠른-시작)
- [API 문서](#-api-문서)
- [배포](#-배포)
- [모니터링](#-모니터링)

## 🎯 프로젝트 개요

TravelOnNa AI 추천시스템은 **협업 필터링(ALS Algorithm)**을 기반으로 사용자의 여행 취향을 분석하여 개인화된 여행지를 추천하는 마이크로서비스입니다.

### 핵심 특징
- 🤖 **ALS 기반 협업 필터링**: 사용자-아이템 상호작용 데이터 학습
- 🗺️ **지역별 특화 모델**: 수도권/강원/영남/호남/제주 지역별 최적화
- ⚡ **실시간 추천**: FastAPI 기반 고성능 API 서비스
- 🔄 **자동 배치 처리**: 주기적 모델 업데이트 및 재학습
- 🐳 **컨테이너 기반**: Docker/Kubernetes 배포 지원

## 🏗️ 시스템 아키텍처

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend       │    │   AI Service    │
│   (React)       │ -> │   (Spring)      │ -> │   (FastAPI)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                       ┌─────────────────┐            │
                       │     MySQL       │ <----------┘
                       │   (User Data)   │
                       └─────────────────┘
                                │
                       ┌─────────────────┐
                       │      Redis      │
                       │   (Caching)     │
                       └─────────────────┘
```

## ✨ 주요 기능

### 1. 개인화 추천
- **협업 필터링**: ALS(Alternating Least Squares) 알고리즘 활용
- **지역별 모델**: 수도권, 강원, 영남, 호남, 제주 지역별 특화
- **실시간 추천**: 사용자 요청 시 즉시 추천 결과 제공

### 2. 데이터 전처리
- **지역별 데이터 분석**: 각 지역 특성 반영한 전처리 파이프라인
- **사용자-아이템 매트릭스**: 협업 필터링을 위한 sparse matrix 생성
- **데이터 품질 관리**: 이상치 제거 및 정규화

### 3. 배치 처리
- **모델 재학습**: 새로운 사용자 데이터 기반 주기적 학습
- **성능 모니터링**: 추천 정확도 및 시스템 성능 추적
- **자동화 스케줄링**: cron 기반 배치 작업 실행

## 🔧 기술 스택

### Backend Framework
- **FastAPI 0.104.1**: 고성능 비동기 웹 프레임워크
- **Uvicorn**: ASGI 서버
- **Pydantic**: 데이터 검증 및 설정 관리

### Machine Learning
- **implicit 0.7.2**: ALS 협업 필터링 라이브러리
- **pandas 2.2.2**: 데이터 조작 및 분석
- **numpy 2.0.2**: 수치 계산
- **scikit-learn 1.6.1**: 머신러닝 유틸리티

### Database & Caching
- **MySQL**: 사용자 데이터 및 여행지 정보 저장
- **Redis 5.0.1**: 추천 결과 캐싱
- **SQLAlchemy 2.0.23**: ORM

### DevOps & Deployment
- **Docker**: 컨테이너화
- **Kubernetes**: 오케스트레이션
- **Jenkins**: CI/CD 파이프라인
- **Ansible**: 자동화 배포

## 📁 디렉토리 구조

```
TravelOnNa_AI/
├── README.md                           # 이 파일
├── recommendation-service/            # 추천 서비스 API
│   ├── app/                          # FastAPI 애플리케이션
│   │   ├── main.py                   # 메인 애플리케이션
│   │   ├── api/                      # API 엔드포인트
│   │   ├── services/                 # 비즈니스 로직
│   │   ├── models/                   # 데이터 모델
│   │   └── utils/                    # 유틸리티
│   ├── config/                       # 설정 파일
│   ├── models/                       # 학습된 ML 모델
│   ├── k8s/                         # Kubernetes 매니페스트
│   ├── Dockerfile                    # Docker 빌드 파일
│   ├── docker-compose.yml           # 로컬 개발 환경
│   ├── requirements.txt             # Python 의존성
│   ├── run.py                       # 서비스 실행 스크립트
│   └── batch_runner.py              # 배치 처리 스크립트
└── Guide/                           # 개발 가이드 문서
```

## 🚀 빠른 시작

### 1. 로컬 개발 환경

```bash
# 저장소 클론
git clone <repository-url>
cd TravelOnNa_AI/recommendation-service

# Python 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
export HOST=0.0.0.0
export PORT=8000
export LOG_LEVEL=info

# 서비스 실행
python run.py
```

### 2. Docker Compose 실행

```bash
cd TravelOnNa_AI/recommendation-service

# 전체 스택 실행 (AI 서비스 + Redis)
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

### 3. 서비스 확인

```bash
# 헬스체크
curl http://localhost:8001/health

# API 문서
open http://localhost:8001/docs
```

## 📚 API 문서

### 주요 엔드포인트

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | 서비스 루트 정보 |
| `GET` | `/health` | 헬스체크 |
| `POST` | `/recommendations` | 개인화 추천 |
| `GET` | `/docs` | Swagger UI |

### 추천 API 예시

```bash
# 사용자 추천 요청
curl -X POST "http://localhost:8001/recommendations" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 123,
    "region": "capital",
    "limit": 10
  }'
```

## 🔄 배포

### Jenkins CI/CD 파이프라인

1. **빌드**: Python 문법 검사 및 의존성 체크
2. **Docker 빌드**: Multi-arch 이미지 생성 (amd64/arm64)
3. **푸시**: Docker Registry에 이미지 업로드  
4. **배포**: Ansible을 통한 Kubernetes 배포
5. **검증**: 헬스체크 및 서비스 확인

### Kubernetes 배포

```bash
# ConfigMap 적용
kubectl apply -f k8s/configmap.yaml

# 서비스 배포
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# 배포 상태 확인
kubectl rollout status deployment/travelonna-ai-recommendation-deploy
```

## 📊 모니터링

### 주요 메트릭
- **응답 시간**: API 호출 시 응답 시간 측정
- **처리량**: 초당 추천 요청 수 (RPS)
- **모델 성능**: 추천 정확도 및 다양성 지표
- **시스템 리소스**: CPU, 메모리, 네트워크 사용량

### 로그 확인
```bash
# 서비스 로그
kubectl logs -f deployment/travelonna-ai-recommendation-deploy

# 배치 처리 로그  
docker logs travelonna-recommendation
```

## 🤝 기여하기

1. 이슈 등록 또는 기능 제안
2. 브랜치 생성: `git checkout -b feature/새기능`
3. 변경사항 커밋: `git commit -m '새기능 추가'`
4. 브랜치 푸시: `git push origin feature/새기능`
5. Pull Request 생성

## 📝 라이센스

이 프로젝트는 TravelOnNa 팀의 소유입니다.

## 👥 팀 정보

**TravelOnNa Development Team**
- AI/ML: 추천 알고리즘 개발 및 최적화
- Backend: Spring Boot 기반 메인 서비스
- Frontend: React 기반 사용자 인터페이스
- DevOps: Jenkins/Ansible/Kubernetes 기반 배포 자동화

---
> 🌟 **여행ON나**와 함께 더 나은 여행 경험을 만들어보세요! 