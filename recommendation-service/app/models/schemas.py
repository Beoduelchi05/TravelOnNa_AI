from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class RecommendationType(str, Enum):
    RECORD = "record"
    PLACE = "place"
    PLAN = "plan"

class RecommendationRequest(BaseModel):
    user_id: int = Field(..., gt=0, description="사용자 ID")
    recommendation_type: RecommendationType = Field(
        default=RecommendationType.RECORD, 
        description="추천 타입"
    )
    limit: int = Field(default=10, ge=1, le=50, description="추천 개수")
    filters: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="추가 필터 조건"
    )
    exclude_items: Optional[List[int]] = Field(
        default=None, 
        description="제외할 아이템 ID 목록"
    )

class RecommendationItem(BaseModel):
    item_id: int
    score: float = Field(..., ge=0.0, le=1.0)
    item_type: RecommendationType
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class RecommendationResponse(BaseModel):
    user_id: int
    recommendations: List[RecommendationItem]
    total_count: int
    algorithm_used: str
    generated_at: str
    
class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    model_loaded: bool
    uptime: float

# 백엔드 API 스펙용 새로운 스키마
class SimpleRecommendationItem(BaseModel):
    """백엔드 API용 간단한 추천 아이템"""
    itemId: int
    score: float = Field(..., ge=0.0, le=1.0)

class SimpleRecommendationResponse(BaseModel):
    """백엔드 API용 간단한 추천 응답"""
    userId: int
    itemType: str  # "log", "place", "plan"
    recommendations: List[SimpleRecommendationItem]

class RefreshRequest(BaseModel):
    """모델 업데이트 요청"""
    mode: str = Field(..., pattern="^(full|incremental)$", description="업데이트 모드")

class RefreshResponse(BaseModel):
    """모델 업데이트 응답"""
    status: str
    updatedCount: int
    duration: str 