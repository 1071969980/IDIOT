-- CreateSessionTasksTable
CREATE TABLE IF NOT EXISTS u2a_session_tasks (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    user_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES simple_users(id) ON DELETE CASCADE
);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_session_id ON u2a_session_tasks (session_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_user_id ON u2a_session_tasks (user_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_status ON u2a_session_tasks (status);

-- InsertSessionTask
INSERT INTO u2a_session_tasks (session_id, user_id, status)
VALUES (:session_id, :user_id, :status)
RETURNING id;

-- UpdateSessionTask1
UPDATE u2a_session_tasks
SET :field_name_1 = :field_value_1
WHERE id = :id_value;

-- UpdateSessionTask2
UPDATE u2a_session_tasks
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE id = :id_value;

-- UpdateSessionTask3
UPDATE u2a_session_tasks
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE id = :id_value;

-- UpdateSessionTaskStatus
UPDATE u2a_session_tasks
SET status = :status_value
WHERE id = :id_value;

-- QuerySessionTaskById
SELECT *
FROM u2a_session_tasks
WHERE id = :id_value;

-- QuerySessionTasksBySession
SELECT *
FROM u2a_session_tasks
WHERE session_id = :session_id_value
ORDER BY created_at;

-- QuerySessionTaskBySessionAndStatus
SELECT *
FROM u2a_session_tasks
WHERE session_id = :session_id_value AND status = :status_value

-- QuerySessionTasksByUser
SELECT *
FROM u2a_session_tasks
WHERE user_id = :user_id_value
ORDER BY created_at;

-- SessionTaskExists
SELECT COUNT(*)
FROM u2a_session_tasks
WHERE id = :id_value;

-- QuerySessionTaskField1
SELECT :field_name_1
FROM u2a_session_tasks
WHERE id = :id_value;

-- QuerySessionTaskField2
SELECT :field_name_1, :field_name_2
FROM u2a_session_tasks
WHERE id = :id_value;

-- QuerySessionTaskField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM u2a_session_tasks
WHERE id = :id_value;

-- QuerySessionTaskField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM u2a_session_tasks
WHERE id = :id_value;

-- DeleteSessionTask
DELETE FROM u2a_session_tasks
WHERE id = :id_value;

-- DeleteSessionTasksBySession
DELETE FROM u2a_session_tasks
WHERE session_id = :session_id_value;

-- CheckSessionHasTaskWithStatus
SELECT COUNT(*)
FROM u2a_session_tasks
WHERE session_id = :session_id_value AND status = :status_value;

-- CheckSessionHasTaskWithStatuses
SELECT COUNT(*)
FROM u2a_session_tasks
WHERE session_id = :session_id_value AND status IN (:status_values);

-- GetSessionTaskStatusCounts
SELECT status, COUNT(*) as count
FROM u2a_session_tasks
WHERE session_id = :session_id_value
GROUP BY status;