-- 여행ON나 AI 추천 시스템 필수 테이블 생성 스크립트

-- 1. recommendations 테이블 (추천 결과 저장)
CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    item_id INT NOT NULL,
    item_type ENUM('log', 'place', 'plan') NOT NULL DEFAULT 'log',
    score FLOAT NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_item_type (user_id, item_type),
    INDEX idx_score (score DESC),
    INDEX idx_created_at (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. recommendation_batch_logs 테이블 (배치 처리 로그)
CREATE TABLE IF NOT EXISTS recommendation_batch_logs (
    batch_id INT AUTO_INCREMENT PRIMARY KEY,
    batch_type ENUM('full', 'incremental') NOT NULL,
    total_users INT NOT NULL DEFAULT 0,
    processed_users INT NOT NULL DEFAULT 0,
    total_recommendations INT NOT NULL DEFAULT 0,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP NULL,
    status ENUM('running', 'completed', 'failed') NOT NULL DEFAULT 'running',
    error_message TEXT NULL,
    INDEX idx_batch_type (batch_type),
    INDEX idx_status (status),
    INDEX idx_start_time (start_time DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 데이터 확인 쿼리들
SELECT 'Checking recommendations table...' as status;
SELECT COUNT(*) as recommendation_count FROM recommendations;

SELECT 'Checking recommendation_batch_logs table...' as status;  
SELECT COUNT(*) as batch_log_count FROM recommendation_batch_logs;

SELECT 'Checking user_actions data...' as status;
SELECT 
    COUNT(*) as total_actions,
    COUNT(DISTINCT user_id) as unique_users,
    COUNT(DISTINCT target_id) as unique_items
FROM user_actions; 