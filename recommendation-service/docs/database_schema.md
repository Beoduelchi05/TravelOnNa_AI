# Database Schema for Recommendation Service

## 추천 결과 저장 테이블

### recommendations 테이블
```sql
CREATE TABLE recommendations (
    recommendation_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    item_id INT NOT NULL,
    item_type ENUM('log', 'place', 'plan') NOT NULL,
    score FLOAT NOT NULL,
    rank_position INT NOT NULL,
    algorithm_type ENUM('als', 'popularity', 'hybrid') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_user_item_type (user_id, item_type, rank_position),
    INDEX idx_user_created (user_id, created_at DESC),
    INDEX idx_item_score (item_id, score DESC),
    
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE
);
```

### 배치 처리 로그 테이블
```sql
CREATE TABLE recommendation_batch_logs (
    batch_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    batch_type ENUM('full', 'incremental') NOT NULL,
    total_users INT NOT NULL,
    processed_users INT NOT NULL,
    total_recommendations INT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NULL,
    status ENUM('running', 'completed', 'failed') NOT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 백엔드 연동 방식

### 1. 추천 조회 (백엔드에서 구현)
```sql
-- 사용자별 로그 추천 조회
SELECT item_id, score, rank_position 
FROM recommendations 
WHERE user_id = ? AND item_type = 'log'
ORDER BY rank_position ASC 
LIMIT 10;

-- 새로운 사용자 fallback (인기 기록)
SELECT l.log_id, (COUNT(DISTINCT lk.user_id) * 3 + COUNT(DISTINCT lc.loco_id) * 2) as score
FROM log l
LEFT JOIN likes lk ON l.log_id = lk.log_id  
LEFT JOIN log_comment lc ON l.log_id = lc.log_id
WHERE l.is_public = 1 AND l.created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
GROUP BY l.log_id
ORDER BY score DESC
LIMIT 10;
```

### 2. 배치 처리 스케줄 (추천 서비스)
- **전체 업데이트**: 매일 새벽 2시
- **증분 업데이트**: 6시간마다
- **실시간 트리거**: 특정 이벤트 발생 시

## 성능 최적화

### 파티셔닝 전략
```sql
-- user_id 기반 파티셔닝 (대용량 데이터 대비)
ALTER TABLE recommendations 
PARTITION BY HASH(user_id) 
PARTITIONS 8;
```

### 데이터 정리 정책
```sql
-- 30일 이상 된 추천 결과 삭제
DELETE FROM recommendations 
WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
``` 