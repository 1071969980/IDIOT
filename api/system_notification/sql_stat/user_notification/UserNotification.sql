-- CreateTablesAndIndexes
CREATE TABLE IF NOT EXISTS user_notifications (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_id UUID NOT NULL REFERENCES simple_users(id) ON DELETE CASCADE,
    level TEXT NOT NULL DEFAULT 'Normal' CHECK (level IN ('Low', 'Normal', 'High', 'Urgent')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);
--
CREATE INDEX IF NOT EXISTS idx_user_notifications_user
    ON user_notifications (user_id);
--
CREATE INDEX IF NOT EXISTS idx_user_notifications_user_active
    ON user_notifications (user_id) WHERE deleted_at IS NULL;
--
CREATE OR REPLACE FUNCTION user_notification_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE TRIGGER user_notification_before_update
BEFORE UPDATE ON user_notifications
FOR EACH ROW
EXECUTE FUNCTION user_notification_update_timestamp();

-- InsertNotification
INSERT INTO user_notifications (user_id, level, content)
VALUES (:user_id, :level, :content)
RETURNING id, user_id, level, content, created_at, updated_at, deleted_at;

-- GetActiveByUserId
SELECT id, user_id, level, content, created_at, updated_at, deleted_at
FROM user_notifications
WHERE user_id = :user_id AND deleted_at IS NULL
ORDER BY created_at DESC;

-- SoftDelete
UPDATE user_notifications
SET deleted_at = NOW()
WHERE id = :notification_id AND user_id = :user_id AND deleted_at IS NULL;
