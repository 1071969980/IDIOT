-- CreateTable
CREATE TABLE IF NOT EXISTS user_pod_records (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_id UUID NOT NULL REFERENCES simple_users(id) ON DELETE CASCADE,
    image VARCHAR(512) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL CHECK (status IN ('creating', 'running', 'stopping', 'stopped', 'error')),
    create_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    unload_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    pod_name VARCHAR(255) NOT NULL,
    namespace VARCHAR(255) NOT NULL DEFAULT 'idiot-user-space'
);
--
DROP INDEX IF EXISTS idx_user_pod_records_user_id;
--
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_pod_records_user_id_image ON user_pod_records (user_id, image);
--
CREATE INDEX IF NOT EXISTS idx_user_pod_records_status ON user_pod_records (status);
--
CREATE INDEX IF NOT EXISTS idx_user_pod_records_heartbeat_at ON user_pod_records (heartbeat_at);

-- InsertRecord
INSERT INTO user_pod_records (user_id, image, status, pod_name, namespace)
VALUES (:user_id, :image, :status, :pod_name, :namespace)
RETURNING id;

-- QueryRecordByUserIdAndImage
SELECT * FROM user_pod_records WHERE user_id = :user_id_value AND image = :image_value;

-- QueryRecordsByUserId
SELECT * FROM user_pod_records WHERE user_id = :user_id_value;

-- QueryRecordById
SELECT * FROM user_pod_records WHERE id = :id_value;

-- UpdateHeartbeat
UPDATE user_pod_records
SET heartbeat_at = CURRENT_TIMESTAMP
WHERE user_id = :user_id_value AND image = :image_value;

-- UpdateStatus
UPDATE user_pod_records
SET status = :status_value, error_message = :error_message_value
WHERE user_id = :user_id_value AND image = :image_value;

-- UpdateStatusAndUnload
UPDATE user_pod_records
SET status = :status_value, unload_at = CURRENT_TIMESTAMP, error_message = :error_message_value
WHERE user_id = :user_id_value AND image = :image_value;

-- QueryTimeoutRecords
SELECT * FROM user_pod_records
WHERE status = 'running'
AND heartbeat_at < :heartbeat_threshold;

-- QueryAllRunningRecords
SELECT * FROM user_pod_records WHERE status = 'running';

-- DeleteRecordByUserIdAndImage
DELETE FROM user_pod_records WHERE user_id = :user_id_value AND image = :image_value;

-- DeleteRecordsByUserId
DELETE FROM user_pod_records WHERE user_id = :user_id_value;

-- QueryRecordLifetime
SELECT
    id, user_id, status, create_at, heartbeat_at, unload_at,
    EXTRACT(EPOCH FROM (COALESCE(unload_at, CURRENT_TIMESTAMP) - create_at)) as lifetime_seconds
FROM user_pod_records
WHERE user_id = :user_id_value AND image = :image_value;
