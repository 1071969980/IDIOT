-- CreateTablesAndIndexes
CREATE TABLE IF NOT EXISTS session_notifications (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    user_id UUID NOT NULL,
    level TEXT NOT NULL DEFAULT 'Normal' CHECK (level IN ('Low', 'Normal', 'High', 'Urgent')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);
--
CREATE INDEX IF NOT EXISTS idx_session_notifications_session
    ON session_notifications (session_id);
--
CREATE INDEX IF NOT EXISTS idx_session_notifications_active
    ON session_notifications (session_id) WHERE deleted_at IS NULL;
--
CREATE OR REPLACE FUNCTION session_notification_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE TRIGGER session_notification_before_update
BEFORE UPDATE ON session_notifications
FOR EACH ROW
EXECUTE FUNCTION session_notification_update_timestamp();

-- InsertNotification
INSERT INTO session_notifications (session_id, user_id, level, content)
VALUES (:session_id, :user_id, :level, :content)
RETURNING id, session_id, user_id, level, content, created_at, updated_at, deleted_at;

-- session_id 已关联唯一用户，查询只需 session_id
-- GetActiveBySessionId
SELECT id, session_id, user_id, level, content, created_at, updated_at, deleted_at
FROM session_notifications
WHERE session_id = :session_id AND deleted_at IS NULL
ORDER BY created_at DESC;

-- session_id 已关联唯一用户，但同时校验 session_id 确保归属关系正确
-- SoftDelete
UPDATE session_notifications
SET deleted_at = NOW()
WHERE id = :notification_id AND session_id = :session_id AND deleted_at IS NULL;
