from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import uvicorn
from contextlib import asynccontextmanager

from app.api.recommendation import router as recommendation_router
from app.models.schemas import HealthResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 애플리케이션 시작 시간
start_time = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 실행
    logger.info("🚀 추천 서비스 시작")
    yield
    # 종료 시 실행  
    logger.info("🛑 추천 서비스 종료")

app = FastAPI(
    title="Travel Recommendation Service",
    description="여행ON나 AI 추천 시스템",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 운영에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 미들웨어: 요청 로깅
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time_req = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time_req
    
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )
    return response

# 라우터 등록
app.include_router(recommendation_router)

@app.get("/", response_model=HealthResponse)
async def root():
    """루트 엔드포인트"""
    return HealthResponse(
        status="healthy",
        service="recommendation",
        version="1.0.0",
        model_loaded=True,  # 임시로 True
        uptime=time.time() - start_time
    )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """헬스체크 엔드포인트"""
    return HealthResponse(
        status="healthy",
        service="recommendation",
        version="1.0.0", 
        model_loaded=True,  # 임시로 True
        uptime=time.time() - start_time
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """전역 예외 핸들러"""
    logger.error(f"예상치 못한 오류: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "내부 서버 오류가 발생했습니다."}
    )

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # 운영환경에서는 False
        log_level="info"
    ) 