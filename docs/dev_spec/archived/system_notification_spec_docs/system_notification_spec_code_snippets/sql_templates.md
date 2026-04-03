# SQL模板文件

SQL模板遵循项目已有规范，使用 `-- LabelName` 注释分隔，由 `parse_sql_file` 解析。完整规范参见 [system_notification_spec_context.md](../system_notification_spec_context.md#11-sql模板系统)。

## SystemNotification.sql

文件位置：`api/system_notification/sql_stat/system_notification/SystemNotification.sql`

```sql
-- CreateTablesAndIndexes
CREATE TABLE IF NOT EXISTS system_notifications (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    level TEXT NOT NULL DEFAULT 'info',
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
```

## SystemNotificationAck.sql

文件位置：`api/system_notification/sql_stat/system_notification_ack/SystemNotificationAck.sql`

```sql
-- CreateTablesAndIndexes
CREATE TABLE IF NOT EXISTS system_notification_acks (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    notification_id UUID NOT NULL REFERENCES system_notifications(id),
    user_id UUID NOT NULL,
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

-- GetUnackedNotifications
-- 使用 NOT EXISTS 替代 LEFT JOIN，配合 (user_id, notification_id) 复合索引，
-- 子查询可走索引直接定位，避免全表 JOIN。
SELECT sn.id, sn.level, sn.content, sn.created_at, sn.updated_at
FROM system_notifications sn
WHERE NOT EXISTS (
    SELECT 1 FROM system_notification_acks sna
    WHERE sna.notification_id = sn.id AND sna.user_id = :user_id
)
ORDER BY sn.created_at DESC;
```

## UserNotification.sql

文件位置：`api/system_notification/sql_stat/user_notification/UserNotification.sql`

```sql
-- CreateTablesAndIndexes
CREATE TABLE IF NOT EXISTS user_notifications (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_id UUID NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
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
```

## SessionNotification.sql

文件位置：`api/system_notification/sql_stat/session_notification/SessionNotification.sql`

```sql
-- CreateTablesAndIndexes
CREATE TABLE IF NOT EXISTS session_notifications (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    user_id UUID NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
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

-- InsertNotification
INSERT INTO session_notifications (session_id, user_id, level, content)
VALUES (:session_id, :user_id, :level, :content)
RETURNING id, session_id, user_id, level, content, created_at, updated_at, deleted_at;

-- GetActiveBySessionId
-- session_id 已关联唯一用户，查询只需 session_id
SELECT id, session_id, user_id, level, content, created_at, updated_at, deleted_at
FROM session_notifications
WHERE session_id = :session_id AND deleted_at IS NULL
ORDER BY created_at DESC;

-- SoftDelete
-- session_id 已关联唯一用户，但同时校验 session_id 确保归属关系正确
UPDATE session_notifications
SET deleted_at = NOW()
WHERE id = :notification_id AND session_id = :session_id AND deleted_at IS NULL;
```
