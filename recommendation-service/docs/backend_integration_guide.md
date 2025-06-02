# 백엔드 연동 가이드 - 배치 기반 추천 시스템

## 📋 개요

추천 서비스는 **배치 처리 방식**으로 동작하며, 스프링 백엔드는 `recommendations` 테이블에서 미리 계산된 추천 결과를 조회하는 방식입니다.

## 🗄️ 필요한 테이블 생성

### 1. recommendations 테이블
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

### 2. recommendation_batch_logs 테이블 (모니터링용)
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

## 🔧 백엔드 API 구현

### 1. 사용자 추천 조회 API

#### Spring Controller 예시
```java
@RestController
@RequestMapping("/api/v1/recommendations")
public class RecommendationController {
    
    @Autowired
    private RecommendationService recommendationService;
    
    @GetMapping
    public ResponseEntity<RecommendationResponse> getRecommendations(
            @RequestParam Integer userId,
            @RequestParam(defaultValue = "log") String type,
            @RequestParam(defaultValue = "10") Integer limit) {
        
        List<RecommendationItem> recommendations = 
            recommendationService.getRecommendations(userId, type, limit);
            
        return ResponseEntity.ok(RecommendationResponse.builder()
            .userId(userId)
            .itemType(type)
            .recommendations(recommendations)
            .build());
    }
}
```

#### Service 구현
```java
@Service
public class RecommendationService {
    
    @Autowired
    private RecommendationRepository recommendationRepository;
    
    @Autowired 
    private LogRepository logRepository;
    
    public List<RecommendationItem> getRecommendations(
            Integer userId, String itemType, Integer limit) {
        
        // 1. 추천 테이블에서 조회
        List<Recommendation> recs = recommendationRepository
            .findByUserIdAndItemTypeOrderByRankPosition(userId, itemType, limit);
        
        if (!recs.isEmpty()) {
            return recs.stream()
                .map(this::convertToRecommendationItem)
                .collect(Collectors.toList());
        }
        
        // 2. 새로운 사용자인 경우 인기 기록으로 fallback
        return getPopularItems(itemType, limit);
    }
    
    private List<RecommendationItem> getPopularItems(String itemType, Integer limit) {
        // 인기도 기반 추천
        String sql = """
            SELECT l.log_id, 
                   (COUNT(DISTINCT lk.user_id) * 3 + COUNT(DISTINCT lc.loco_id) * 2) as score
            FROM log l
            LEFT JOIN likes lk ON l.log_id = lk.log_id  
            LEFT JOIN log_comment lc ON l.log_id = lc.log_id
            WHERE l.is_public = 1 
              AND l.created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
            GROUP BY l.log_id
            HAVING score > 0
            ORDER BY score DESC, l.created_at DESC
            LIMIT ?
            """;
        
        // JdbcTemplate 또는 QueryDsl 사용하여 실행
        // ...
    }
}
```

### 2. Repository 구현

#### JPA Repository
```java
@Repository
public interface RecommendationRepository extends JpaRepository<Recommendation, Long> {
    
    @Query("SELECT r FROM Recommendation r " +
           "WHERE r.userId = :userId AND r.itemType = :itemType " +
           "ORDER BY r.rankPosition ASC")
    List<Recommendation> findByUserIdAndItemTypeOrderByRankPosition(
        @Param("userId") Integer userId,
        @Param("itemType") String itemType,
        Pageable pageable
    );
    
    @Query("SELECT r FROM Recommendation r " +
           "WHERE r.userId = :userId AND r.createdAt >= :since " +
           "ORDER BY r.rankPosition ASC")
    List<Recommendation> findByUserIdAndCreatedAtAfter(
        @Param("userId") Integer userId,
        @Param("since") LocalDateTime since
    );
}
```

#### Entity 클래스
```java
@Entity
@Table(name = "recommendations")
public class Recommendation {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "recommendation_id")
    private Long id;
    
    @Column(name = "user_id", nullable = false)
    private Integer userId;
    
    @Column(name = "item_id", nullable = false)
    private Integer itemId;
    
    @Enumerated(EnumType.STRING)
    @Column(name = "item_type", nullable = false)
    private ItemType itemType;
    
    @Column(name = "score", nullable = false)
    private Float score;
    
    @Column(name = "rank_position", nullable = false)
    private Integer rankPosition;
    
    @Enumerated(EnumType.STRING)
    @Column(name = "algorithm_type", nullable = false)
    private AlgorithmType algorithmType;
    
    @Column(name = "created_at")
    private LocalDateTime createdAt;
    
    // getters, setters, constructors...
}

enum ItemType {
    LOG, PLACE, PLAN
}

enum AlgorithmType {
    ALS, POPULARITY, HYBRID
}
```

## 📊 배치 처리 모니터링

### 배치 상태 조회 API
```java
@GetMapping("/batch/status")
public ResponseEntity<BatchStatusResponse> getBatchStatus() {
    
    BatchLog latestBatch = batchLogRepository
        .findTopByOrderByCreatedAtDesc();
    
    return ResponseEntity.ok(BatchStatusResponse.builder()
        .batchId(latestBatch.getBatchId())
        .batchType(latestBatch.getBatchType())
        .status(latestBatch.getStatus())
        .processedUsers(latestBatch.getProcessedUsers())
        .totalUsers(latestBatch.getTotalUsers())
        .totalRecommendations(latestBatch.getTotalRecommendations())
        .startTime(latestBatch.getStartTime())
        .endTime(latestBatch.getEndTime())
        .build());
}
```

## 🔄 배치 처리 운영

### 1. 스케줄러 시작 (서버에서)
```bash
# 데몬 모드로 스케줄러 시작
nohup python batch_runner.py --mode scheduler > batch.log 2>&1 &

# 또는 systemd 서비스로 등록
sudo systemctl start travelonna-recommendation-batch
```

### 2. 수동 배치 실행
```bash
# 전체 배치 처리
python batch_runner.py --mode full

# 증분 배치 처리  
python batch_runner.py --mode incremental
```

### 3. 모니터링 쿼리
```sql
-- 최근 배치 상태 확인
SELECT * FROM recommendation_batch_logs 
ORDER BY created_at DESC 
LIMIT 5;

-- 사용자별 추천 개수 확인
SELECT user_id, item_type, COUNT(*) as rec_count
FROM recommendations 
GROUP BY user_id, item_type
ORDER BY rec_count DESC
LIMIT 10;

-- 알고리즘별 추천 분포
SELECT algorithm_type, COUNT(*) as count
FROM recommendations 
GROUP BY algorithm_type;
```

## 🚀 성능 최적화

### 1. 인덱스 최적화
```sql
-- 사용자별 빠른 조회를 위한 복합 인덱스
CREATE INDEX idx_user_item_type_rank 
ON recommendations (user_id, item_type, rank_position);

-- 시간 기반 조회용 인덱스  
CREATE INDEX idx_created_at_desc 
ON recommendations (created_at DESC);
```

### 2. 캐싱 전략
```java
// Redis 캐싱 적용
@Cacheable(value = "user_recommendations", key = "#userId + '_' + #itemType")
public List<RecommendationItem> getRecommendations(Integer userId, String itemType, Integer limit) {
    // ...
}

// 캐시 무효화 (배치 완료 후)
@CacheEvict(value = "user_recommendations", allEntries = true)
public void clearRecommendationCache() {
    // 배치 완료 시 호출
}
```

### 3. 데이터 정리
```sql
-- 30일 이상 된 추천 삭제 (cron job)
DELETE FROM recommendations 
WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

-- 완료된 배치 로그 정리 (3개월 이상)
DELETE FROM recommendation_batch_logs 
WHERE created_at < DATE_SUB(NOW(), INTERVAL 3 MONTH) 
  AND status = 'completed';
```

## ⚠️ 장애 대응

### 1. 추천 데이터가 없는 경우
- 인기 기록으로 fallback
- 빈 결과 반환하지 말고 기본 추천 제공

### 2. 배치 처리 실패 시
- 배치 로그에서 오류 확인
- 수동으로 증분 배치 재실행
- 필요시 전체 배치 재실행

### 3. 성능 이슈 시
- 추천 개수 제한 (사용자당 최대 20개)
- 오래된 추천 데이터 정리
- 인덱스 최적화 확인 