-- CreateTablesAndIndexes
CREATE TABLE IF NOT EXISTS system_notifications (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    level TEXT NOT NULL DEFAULT 'Normal' CHECK (level IN ('Low', 'Normal', 'High', 'Urgent')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
--
CREATE INDEX IF NOT EXISTS idx_system_notifications_created_at
    ON system_notifications (created_at DESC);
--
CREATE OR REPLACE FUNCTION system_notification_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE TRIGGER system_notification_before_update
BEFORE UPDATE ON system_notifications
FOR EACH ROW
EXECUTE FUNCTION system_notification_update_timestamp();

-- InsertNotification
INSERT INTO system_notifications (level, content)
VALUES (:level, :content)
RETURNING id, level, content, created_at, updated_at;

-- GetAllNotifications
SELECT id, level, content, created_at, updated_at
FROM system_notifications
ORDER BY created_at DESC
LIMIT :limit OFFSET :offset;
