from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from typing import List, Optional
import time
from app.models.schemas import (
    RecommendationRequest, 
    RecommendationResponse, 
    RecommendationItem,
    RecommendationType,
    SimpleRecommendationResponse,
    SimpleRecommendationItem,
    RefreshRequest,
    RefreshResponse
)
from app.utils.logger import get_logger
from app.services.database_service import DatabaseService
from app.services.als_service import ALSRecommendationService

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["recommendations"])

# ALS 서비스 인스턴스 (전역으로 한 번만 로드)
als_service = None

def get_als_service():
    """ALS 서비스 인스턴스를 반환 (lazy loading)"""
    global als_service
    if als_service is None:
        try:
            logger.info("ALS 서비스 초기화 중...")
            # 올바른 모델 경로 지정
            als_service = ALSRecommendationService(model_path="./models")
            if not als_service.is_loaded:
                logger.warning("⚠️ ALS 모델 로딩 실패 - 백업 방식 사용")
                als_service = None
        except Exception as e:
            logger.error(f"❌ ALS 서비스 초기화 실패: {str(e)}")
            als_service = None
    return als_service

@router.get("/test")
async def test_endpoint():
    """테스트 엔드포인트"""
    als = get_als_service()
    model_status = "loaded" if als and als.is_loaded else "not_loaded"
    return {
        "message": "추천 서비스가 정상 작동 중입니다!", 
        "timestamp": datetime.now().isoformat(),
        "als_model_status": model_status
    }

# 백엔드 API 스펙에 맞는 새로운 엔드포인트
@router.get("/recommendations", response_model=SimpleRecommendationResponse)
async def get_recommendations(
    userId: int = Query(..., description="사용자 ID"),
    type: str = Query(..., description="추천 타입 (log, place, plan)"),
    limit: int = Query(default=10, ge=1, le=50, description="추천 개수")
):
    """백엔드 API 스펙용 추천 조회 (GET 방식)"""
    try:
        logger.info(f"백엔드 API 추천 요청: userId={userId}, type={type}, limit={limit}")
        
        # type 매핑 (log -> record)
        type_mapping = {
            "log": RecommendationType.RECORD,
            "place": RecommendationType.PLACE,
            "plan": RecommendationType.PLAN
        }
        
        if type not in type_mapping:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 타입: {type}")
        
        rec_type = type_mapping[type]
        
        # ALS 서비스로 추천 생성
        als = get_als_service()
        
        if als and als.is_loaded:
            recommendations, algorithm_used = als.get_recommendations(
                user_id=userId,
                rec_type=rec_type,
                limit=limit
            )
            logger.info(f"✅ ALS 추천 생성: {len(recommendations)}개")
        else:
            # ALS 모델 실패 시 백업: 인기도 기반
            logger.warning("⚠️ ALS 모델 사용 불가 - 인기도 기반으로 백업")
            db = DatabaseService()
            popular_items = db.get_popular_items(rec_type.value, limit * 2)
            selected_items = popular_items[:limit]
            
            recommendations = []
            for i, item_id in enumerate(selected_items):
                score = max(0.1, 1.0 - (i * 0.1))
                recommendations.append(
                    RecommendationItem(
                        item_id=item_id,
                        score=score,
                        item_type=rec_type
                    )
                )
        
        # 백엔드 API 스펙에 맞게 변환
        simple_recommendations = [
            SimpleRecommendationItem(
                itemId=rec.item_id,
                score=rec.score
            )
            for rec in recommendations
        ]
        
        response = SimpleRecommendationResponse(
            userId=userId,
            itemType=type,  # 원래 요청한 타입 그대로 반환
            recommendations=simple_recommendations
        )
        
        logger.info(f"백엔드 API 추천 완료: {len(simple_recommendations)}개 아이템")
        return response
        
    except Exception as e:
        logger.error(f"백엔드 API 추천 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"추천 생성 실패: {str(e)}")

@router.post("/recommendations/refresh", response_model=RefreshResponse)
async def refresh_recommendations(request: RefreshRequest):
    """모델 업데이트 / 추천 업데이트"""
    try:
        start_time = time.time()
        logger.info(f"추천 업데이트 시작: mode={request.mode}")
        
        als = get_als_service()
        
        if request.mode == "full":
            # 전체 업데이트
            if als and als.is_loaded:
                # 현재 데이터베이스에서 모든 사용자의 상호작용 데이터 재로드
                als._rebuild_mappings()
                als._load_item_metadata()
                updated_count = len(als.user_id_map) + len(als.item_id_map)
                logger.info(f"✅ 전체 업데이트 완료: 사용자 {len(als.user_id_map)}명, 아이템 {len(als.item_id_map)}개")
            else:
                # ALS 모델이 없으면 데이터베이스만 업데이트
                db = DatabaseService()
                interactions = db.get_user_item_interactions()
                updated_count = len(interactions)
                logger.info(f"✅ 데이터베이스 업데이트 완료: {updated_count}건")
                
        elif request.mode == "incremental":
            # 증분 업데이트 (간단 구현)
            if als and als.is_loaded:
                # 메타데이터만 업데이트
                als._load_item_metadata()
                updated_count = len(als.item_metadata)
                logger.info(f"✅ 증분 업데이트 완료: 메타데이터 {updated_count}개")
            else:
                updated_count = 0
                logger.warning("⚠️ ALS 모델이 로드되지 않아 증분 업데이트 불가")
        
        duration = time.time() - start_time
        
        response = RefreshResponse(
            status="success",
            updatedCount=updated_count,
            duration=f"{duration:.1f}s"
        )
        
        logger.info(f"추천 업데이트 완료: {request.mode} 모드, {updated_count}개 업데이트, {duration:.1f}초")
        return response
        
    except Exception as e:
        logger.error(f"추천 업데이트 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"업데이트 실패: {str(e)}")

@router.get("/database/test")
async def test_database():
    """데이터베이스 연결 테스트"""
    try:
        db = DatabaseService()
        interactions = db.get_user_item_interactions()
        popular = db.get_popular_items("record", 3)
        metadata = db.get_item_metadata(popular[:2])
        
        # ALS 모델 상태도 확인
        als = get_als_service()
        model_info = als.get_model_info() if als and als.is_loaded else {"status": "not_loaded"}
        
        return {
            "database_status": "connected",
            "interactions_count": len(interactions),
            "popular_items": popular,
            "metadata_count": len(metadata),
            "sample_metadata": list(metadata.values())[:1] if metadata else None,
            "als_model_info": model_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"테스트 실패: {str(e)}")

# 기존 API (호환성 유지)
@router.post("/recommendations", response_model=RecommendationResponse)
async def create_recommendations(request: RecommendationRequest):
    """통합 추천 API (ALS 모델 기반) - 기존 호환성용"""
    try:
        logger.info(f"ALS 추천 요청: user_id={request.user_id}, type={request.recommendation_type}")
        
        # ALS 서비스 가져오기
        als = get_als_service()
        
        if als and als.is_loaded:
            # ALS 모델 사용
            recommendations, algorithm_used = als.get_recommendations(
            user_id=request.user_id,
            rec_type=request.recommendation_type,
            limit=request.limit,
            filters=request.filters,
            exclude_items=request.exclude_items
        )
            logger.info(f"✅ ALS 모델로 추천 생성: {len(recommendations)}개")
            
        else:
            # ALS 모델 로딩 실패 시 백업: 인기도 기반
            logger.warning("⚠️ ALS 모델 사용 불가 - 인기도 기반으로 백업")
            db = DatabaseService()
            popular_items = db.get_popular_items(request.recommendation_type.value, request.limit * 2)
            
            if request.exclude_items:
                popular_items = [item for item in popular_items if item not in request.exclude_items]
            
            selected_items = popular_items[:request.limit]
            metadata_dict = db.get_item_metadata(selected_items)
            
            recommendations = []
            for i, item_id in enumerate(selected_items):
                metadata = metadata_dict.get(str(item_id), {})
                score = max(0.1, 1.0 - (i * 0.1))
                
                recommendations.append(
                    RecommendationItem(
                        item_id=item_id,
                        score=score,
                        item_type=request.recommendation_type,
                        title=metadata.get("title", f"아이템 {item_id}"),
                        description=metadata.get("description", ""),
                        metadata={
                            "method": "popularity_fallback",
                            "rank": i + 1,
                            "author_name": metadata.get("author_name"),
                            "author_nickname": metadata.get("author_nickname"),
                            "like_count": metadata.get("extra", {}).get("like_count", 0),
                            "comment_count": metadata.get("extra", {}).get("comment_count", 0)
                        }
                    )
                )
            algorithm_used = "popularity_fallback"
        
        response = RecommendationResponse(
            user_id=request.user_id,
            recommendations=recommendations,
            total_count=len(recommendations),
            algorithm_used=algorithm_used,
            generated_at=datetime.now().isoformat()
        )
        
        logger.info(f"추천 생성 완료: {len(recommendations)}개 아이템 (알고리즘: {algorithm_used})")
        return response
        
    except Exception as e:
        logger.error(f"추천 생성 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"추천 생성 실패: {str(e)}")

@router.get("/recommendations/records/{user_id}", response_model=RecommendationResponse)
async def get_record_recommendations(
    user_id: int, 
    limit: int = 10,
    exclude_items: str = None
):
    """기록 추천 전용 API"""
    exclude_list = []
    if exclude_items:
        try:
            exclude_list = [int(x.strip()) for x in exclude_items.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="exclude_items 형식이 올바르지 않습니다")
    
    request = RecommendationRequest(
        user_id=user_id,
        recommendation_type=RecommendationType.RECORD,
        limit=limit,
        exclude_items=exclude_list
    )
    return await create_recommendations(request)

@router.get("/model/info")
async def get_model_info():
    """ALS 모델 정보 조회"""
    als = get_als_service()
    if als and als.is_loaded:
        return als.get_model_info()
    else:
        return {"status": "model_not_loaded", "message": "ALS 모델이 로드되지 않았습니다"}

# ===== 배치 처리 API =====

@router.post("/batch/trigger")
async def trigger_batch(
    batch_type: str = Query(default="incremental", description="배치 타입: full 또는 incremental"),
    user_limit: int = Query(default=None, description="처리할 최대 사용자 수 (full batch 전용)")
):
    """수동 배치 처리 트리거 (비동기 실행)"""
    if batch_type not in ["full", "incremental"]:
        raise HTTPException(status_code=400, detail="batch_type은 'full' 또는 'incremental'이어야 합니다")
    
    try:
        from app.services.batch_service import BatchService
        import asyncio
        
        batch_service = BatchService()
        
        # 배치 처리를 백그라운드에서 비동기 실행
        async def run_batch_background():
            if batch_type == "full":
                if user_limit:
                    # 사용자 수 제한된 배치
                    success = await batch_service.run_mini_batch(user_limit)
                else:
                    # 전체 배치
                    success = await batch_service.run_full_batch()
            else:
                success = await batch_service.run_incremental_batch()
            
            logger.info(f"🎯 백그라운드 배치 완료: {batch_type}, 성공: {success}")
        
        # 백그라운드 태스크 시작
        asyncio.create_task(run_batch_background())
        
        # 즉시 응답 반환
        return {
            "message": f"{batch_type} 배치 처리가 백그라운드에서 시작되었습니다",
            "batch_type": batch_type,
            "user_limit": user_limit,
            "status": "started",
            "note": "진행상황은 /batch/status API로 확인하세요"
        }
        
    except Exception as e:
        logger.error(f"❌ 배치 처리 시작 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"배치 처리 시작 중 오류가 발생했습니다: {str(e)}")

@router.get("/batch/status")
async def get_batch_status():
    """최근 배치 처리 상태 조회 (파일 로그 기반)"""
    try:
        import os
        from datetime import datetime
        
        log_file = "/app/logs/batch.log"
        batch_logs = []
        
        # 파일 로그가 존재하는지 확인
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                # 최근 10개 로그만 파싱
                recent_lines = lines[-10:] if len(lines) >= 10 else lines
                
                for line in recent_lines:
                    if line.strip():
                        try:
                            # 로그 형식: [2024-01-08 14:30:00] FULL BATCH - Status: completed, Users: 50, Recommendations: 500
                            parts = line.strip().split(" - ")
                            if len(parts) >= 2:
                                timestamp_part = parts[0].replace("[", "").replace("]", "")
                                batch_type = timestamp_part.split()[-2] if "BATCH" in timestamp_part else "unknown"
                                
                                status_info = parts[1]
                                status = "completed" if "completed" in status_info else ("failed" if "failed" in status_info else "unknown")
                                
                                # Users, Recommendations 숫자 추출
                                users = 0
                                recommendations = 0
                                if "Users:" in status_info:
                                    try:
                                        users_part = status_info.split("Users:")[1].split(",")[0].strip()
                                        users = int(users_part)
                                    except:
                                        users = 0
                                
                                if "Recommendations:" in status_info:
                                    try:
                                        rec_part = status_info.split("Recommendations:")[1].split(",")[0].strip()
                                        recommendations = int(rec_part)
                                    except:
                                        recommendations = 0
                                
                                batch_logs.append({
                                    "batch_type": batch_type.lower(),
                                    "timestamp": timestamp_part.split("]")[0].replace("[", ""),
                                    "status": status,
                                    "processed_users": users,
                                    "total_recommendations": recommendations,
                                    "source": "file_log"
                                })
                        except Exception as e:
                            logger.warning(f"로그 라인 파싱 실패: {line.strip()}, 오류: {str(e)}")
                            continue
                            
            except Exception as e:
                logger.error(f"배치 로그 파일 읽기 실패: {str(e)}")
                
        # 최신 순으로 정렬
        batch_logs.reverse()
        
        # 메모리에서 현재 실행 중인 배치 정보도 포함 (간단 구현)
        current_status = {
            "message": f"배치 로그 파일에서 {len(batch_logs)}개의 기록을 발견했습니다" if batch_logs else "배치 실행 기록이 없습니다",
            "log_file_path": log_file,
            "log_file_exists": os.path.exists(log_file),
            "recent_batches": batch_logs
        }
        
        return current_status
        
    except Exception as e:
        logger.error(f"❌ 배치 상태 조회 실패: {str(e)}")
        return {
            "message": f"배치 상태 조회 중 오류 발생: {str(e)}",
            "log_file_path": "/app/logs/batch.log", 
            "log_file_exists": False,
            "recent_batches": []
        } 