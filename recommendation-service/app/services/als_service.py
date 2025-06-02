import pickle
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging
from scipy.sparse import csr_matrix
from app.models.schemas import RecommendationItem, RecommendationType
from app.utils.logger import get_logger
from app.services.database_service import DatabaseService

logger = get_logger(__name__)

class ALSRecommendationService:
    def __init__(self, model_path: str = "/app/models"):
        self.model_path = model_path
        self.model = None
        self.user_item_matrix = None
        self.user_id_map = {}  # user_id -> matrix_index
        self.item_id_map = {}  # item_id -> matrix_index  
        self.reverse_user_map = {}  # matrix_index -> user_id
        self.reverse_item_map = {}  # matrix_index -> item_id
        self.item_metadata = {}
        self.is_loaded = False
        self.db_service = DatabaseService()
        self.load_models()
    
    def load_models(self) -> bool:
        """저장된 ALS 모델 로드 및 데이터 준비"""
        try:
            logger.info("ALS 모델 로딩 시작...")
            
            # ALS 모델 로드
            with open(f"{self.model_path}/als_model.pkl", "rb") as f:
                model_data = pickle.load(f)
            
            # 모델 데이터 구조 확인 및 분리
            if isinstance(model_data, dict):
                # 모델과 메타데이터가 함께 저장된 경우
                self.model = model_data.get('model')
                self.user_id_map = model_data.get('user_id_map', {})
                self.item_id_map = model_data.get('item_id_map', {})
                self.user_item_matrix = model_data.get('user_item_matrix')
            else:
                # 모델만 저장된 경우
                self.model = model_data
                # 데이터베이스에서 매핑 정보 재구성
                self._rebuild_mappings()
            
            # 역방향 매핑 생성
            self.reverse_user_map = {v: k for k, v in self.user_id_map.items()}
            self.reverse_item_map = {v: k for k, v in self.item_id_map.items()}
            
            logger.info(f"✅ ALS 모델 로딩 완료")
            logger.info(f"   - 사용자 수: {len(self.user_id_map)}")
            logger.info(f"   - 아이템 수: {len(self.item_id_map)}")
            logger.info(f"   - 모델 팩터 수: {getattr(self.model, 'n_components', 'N/A')}")
            
            # 아이템 메타데이터 로드 (DB에서)
            self._load_item_metadata()
            
            self.is_loaded = True
            logger.info("🎉 모든 데이터 로딩 완료!")
            return True
            
        except Exception as e:
            logger.error(f"❌ 모델 로딩 실패: {str(e)}")
            self.is_loaded = False
            return False
    
    def _rebuild_mappings(self):
        """데이터베이스에서 user-item 매핑 재구성"""
        logger.info("사용자-아이템 매핑 재구성 중...")
        
        # 실제 데이터베이스에서 상호작용 데이터 조회
        interactions = self.db_service.get_user_item_interactions()
        
        if interactions.empty:
            logger.warning("⚠️ 상호작용 데이터가 없습니다.")
            return
        
        users = sorted(interactions['user_id'].unique())
        items = sorted(interactions['item_id'].unique())
        
        self.user_id_map = {user_id: idx for idx, user_id in enumerate(users)}
        self.item_id_map = {item_id: idx for idx, item_id in enumerate(items)}
        
        # user-item matrix 재구성 (학습 시와 동일한 구조)
        rows = [self.user_id_map[user_id] for user_id in interactions['user_id']]
        cols = [self.item_id_map[item_id] for item_id in interactions['item_id']]
        data = interactions['rating'].values
        
        self.user_item_matrix = csr_matrix(
            (data, (rows, cols)), 
            shape=(len(users), len(items))
        )
        
        logger.info(f"✅ 매핑 재구성 완료: 사용자 {len(users)}명, 아이템 {len(items)}개")
    
    def _load_item_metadata(self):
        """데이터베이스에서 아이템 메타데이터 로드"""
        try:
            self.item_metadata = self.db_service.get_item_metadata(
                list(self.item_id_map.keys())
            )
            logger.info(f"✅ 아이템 메타데이터 로딩 완료: {len(self.item_metadata)}개")
        except Exception as e:
            logger.warning(f"⚠️ 메타데이터 로딩 실패: {str(e)}")
            self.item_metadata = {}
    
    def get_recommendations(
        self, 
        user_id: int, 
        rec_type: RecommendationType = RecommendationType.RECORD,
        limit: int = 10,
        filters: Optional[Dict] = None,
        exclude_items: Optional[List[int]] = None
    ) -> Tuple[List[RecommendationItem], str]:
        """사용자별 추천 생성"""
        
        if not self.is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다.")
        
        exclude_items = exclude_items or []
        
        try:
            if user_id in self.user_id_map:
                # 기존 사용자 - 협업 필터링
                recommendations, algorithm = self._get_collaborative_recommendations(
                    user_id, rec_type, limit, exclude_items
                )
            else:
                # 신규 사용자 - 인기도 기반
                recommendations, algorithm = self._get_popularity_recommendations(
                    rec_type, limit, exclude_items
                )
            
            # 필터 적용
            if filters:
                recommendations = self._apply_filters(recommendations, filters)
            
            return recommendations[:limit], algorithm
            
        except Exception as e:
            logger.error(f"추천 생성 실패 (user_id: {user_id}): {str(e)}")
            # fallback: 인기도 기반 추천
            return self._get_popularity_recommendations(rec_type, limit, exclude_items)
    
    def _get_collaborative_recommendations(
        self, 
        user_id: int, 
        rec_type: RecommendationType, 
        limit: int,
        exclude_items: List[int]
    ) -> Tuple[List[RecommendationItem], str]:
        """협업 필터링 기반 추천"""
        
        logger.info(f"협업 필터링 추천 생성 (user_id: {user_id})")
        
        # 사용자 인덱스 가져오기
        user_idx = self.user_id_map[user_id]
        
        # ALS 모델로 사용자의 아이템 점수 예측
        # model.predict(user_idx, item_indices)를 사용하거나
        # user/item factor를 직접 내적 계산
        user_factors = self.model.user_factors[user_idx]
        item_factors = self.model.item_factors
        
        # 모든 아이템에 대한 점수 계산
        scores = np.dot(item_factors, user_factors)
        
        # 이미 상호작용한 아이템 제외
        user_items = self.user_item_matrix[user_idx].indices
        scores[user_items] = -np.inf
        
        # 제외할 아이템들도 점수를 낮춤
        for item_id in exclude_items:
            if item_id in self.item_id_map:
                item_idx = self.item_id_map[item_id]
                scores[item_idx] = -np.inf
        
        # 상위 아이템 선택
        top_items = np.argsort(scores)[-limit * 2:][::-1]  # 여유분 확보
        
        recommendations = []
        for item_idx in top_items:
            if len(recommendations) >= limit:
                break
                
            item_id = self.reverse_item_map[item_idx]
            score = scores[item_idx]
            
            # 점수가 유효한 경우만 추가
            if score > -np.inf:
                metadata = self.item_metadata.get(str(item_id), {})
                
                recommendation = RecommendationItem(
                    item_id=item_id,
                    score=float(min(max(score, 0.0), 1.0)),  # 0-1 범위로 정규화
                    item_type=rec_type,
                    title=metadata.get("title"),
                    description=metadata.get("description"),
                    image_url=metadata.get("image_url"),
                    metadata={
                        "method": "collaborative_filtering",
                        "als_score": float(score),
                        "popularity_rank": metadata.get("popularity_rank"),
                        **metadata.get("extra", {})
                    }
                )
                recommendations.append(recommendation)
        
        return recommendations, "collaborative_filtering"
    
    def _get_popularity_recommendations(
        self, 
        rec_type: RecommendationType, 
        limit: int,
        exclude_items: List[int]
    ) -> Tuple[List[RecommendationItem], str]:
        """인기도 기반 추천 (콜드 스타트 대응)"""
        
        logger.info(f"인기도 기반 추천 생성 (타입: {rec_type})")
        
        # DB에서 실제 인기 아이템을 가져오거나
        # user-item matrix에서 상호작용이 많은 아이템 순으로 정렬
        if self.user_item_matrix is not None:
            # 각 아이템별 상호작용 수 계산
            item_popularity = np.array(self.user_item_matrix.sum(axis=0)).flatten()
            popular_indices = np.argsort(item_popularity)[::-1]
        else:
            # fallback: DB에서 인기 아이템 조회
            popular_items = self.db_service.get_popular_items(rec_type, limit * 2)
            popular_indices = [self.item_id_map[item_id] for item_id in popular_items 
                             if item_id in self.item_id_map]
        
        recommendations = []
        count = 0
        for item_idx in popular_indices:
            if count >= limit:
                break
                
            item_id = self.reverse_item_map.get(item_idx)
            if not item_id or item_id in exclude_items:
                continue
                
            metadata = self.item_metadata.get(str(item_id), {})
            
            # 인기도 점수 계산
            if self.user_item_matrix is not None:
                popularity_score = item_popularity[item_idx]
                # 정규화 (최대값 기준)
                max_popularity = item_popularity.max()
                normalized_score = float(popularity_score / max_popularity) if max_popularity > 0 else 0.1
            else:
                normalized_score = max(0.1, 1.0 - (count * 0.05))
            
            recommendation = RecommendationItem(
                item_id=int(item_id),
                score=normalized_score,
                item_type=rec_type,
                title=metadata.get("title"),
                description=metadata.get("description"), 
                image_url=metadata.get("image_url"),
                metadata={
                    "method": "popularity_based",
                    "popularity_rank": count + 1,
                    "interaction_count": int(item_popularity[item_idx]) if self.user_item_matrix is not None else 0,
                    **metadata.get("extra", {})
                }
            )
            recommendations.append(recommendation)
            count += 1
        
        return recommendations, "popularity_based"
    
    def _apply_filters(
        self, 
        recommendations: List[RecommendationItem], 
        filters: Dict
    ) -> List[RecommendationItem]:
        """추천 결과에 필터 적용"""
        
        if not filters:
            return recommendations
        
        filtered = []
        for rec in recommendations:
            # 카테고리 필터
            if "category" in filters:
                item_category = rec.metadata.get("category") if rec.metadata else None
                if item_category not in filters["category"]:
                    continue
            
            # 지역 필터  
            if "region" in filters:
                item_region = rec.metadata.get("region") if rec.metadata else None
                if item_region not in filters["region"]:
                    continue
            
            # 최소 점수 필터
            if "min_score" in filters:
                if rec.score < filters["min_score"]:
                    continue
            
            filtered.append(rec)
        
        return filtered
    
    def get_model_info(self) -> Dict:
        """모델 정보 반환"""
        if not self.is_loaded:
            return {"loaded": False}
        
        return {
            "loaded": True,
            "user_count": len(self.user_id_map),
            "item_count": len(self.item_id_map),
            "model_type": "ALS (Alternating Least Squares)",
            "factors": getattr(self.model, 'factors', 'unknown'),
            "regularization": getattr(self.model, 'regularization', 'unknown'),
            "iterations": getattr(self.model, 'iterations', 'unknown'),
            "matrix_shape": self.user_item_matrix.shape if self.user_item_matrix is not None else None
        }