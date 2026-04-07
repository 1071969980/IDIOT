-- CreateTablesAndIndexes
CREATE TABLE IF NOT EXISTS system_notification_acks (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    notification_id UUID NOT NULL REFERENCES system_notifications(id),
    user_id UUID NOT NULL REFERENCES simple_users(id) ON DELETE CASCADE,
    acked_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(notification_id, user_id)
);
--
CREATE INDEX IF NOT EXISTS idx_system_notification_acks_user_notif
    ON system_notification_acks (user_id, notification_id);

-- InsertAck
INSERT INTO system_notification_acks (notification_id, user_id)
VALUES (:notification_id, :user_id)
ON CONFLICT (notification_id, user_id) DO NOTHING
RETURNING id;

-- 使用 NOT EXISTS 替代 LEFT JOIN，配合 (user_id, notification_id) 复合索引，
-- 子查询可走索引直接定位，避免全表 JOIN。
-- GetUnackedNotifications
SELECT sn.id, sn.level, sn.content, sn.created_at, sn.updated_at
FROM system_notifications sn
WHERE NOT EXISTS (
    SELECT 1 FROM system_notification_acks sna
    WHERE sna.notification_id = sn.id AND sna.user_id = :user_id
)
ORDER BY sn.created_at DESC;
