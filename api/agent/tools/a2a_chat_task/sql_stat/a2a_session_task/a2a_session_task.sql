-- CreateTable
CREATE TABLE IF NOT EXISTS a2a_session_tasks (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    priority INT NOT NULL,
    parmas JSONB NOT NULL,
    conclusion TEXT,
    extra_result_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES a2a_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_a2a_session_tasks_session_id ON a2a_session_tasks (session_id);

CREATE INDEX IF NOT EXISTS idx_a2a_session_tasks_status ON a2a_session_tasks (status);

-- CreateTrigger
CREATE OR REPLACE FUNCTION a2a_session_tasks_update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER IF NOT EXISTS trigger_update_a2a_session_tasks_updated_at
    BEFORE UPDATE ON a2a_session_tasks
    FOR EACH ROW
    EXECUTE FUNCTION a2a_session_tasks_update_updated_at_column();

-- InsertSessionTask
INSERT INTO a2a_session_tasks (session_id, status, priority, parmas, conclusion, extra_result_data)
VALUES (:session_id, :status, :priority, :parmas, :conclusion, :extra_result_data)
RETURNING id;

-- UpdateSessionTask1
UPDATE a2a_session_tasks
SET :field_name_1 = :field_value_1
WHERE id = :id_value;

-- UpdateSessionTask2
UPDATE a2a_session_tasks
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE id = :id_value;

-- UpdateSessionTask3
UPDATE a2a_session_tasks
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE id = :id_value;

-- UpdateSessionTaskStatus
UPDATE a2a_session_tasks
SET status = :status_value
WHERE id = :id_value;

-- QuerySessionTaskById
SELECT *
FROM a2a_session_tasks
WHERE id = :id_value;

-- QuerySessionTasksBySession
SELECT *
FROM a2a_session_tasks
WHERE session_id = :session_id_value
ORDER BY priority DESC, created_at ASC;

-- QuerySessionTaskBySessionAndStatus
SELECT *
FROM a2a_session_tasks
WHERE session_id = :session_id_value AND status = :status_value
ORDER BY priority DESC, created_at ASC;

-- QuerySessionTasksByStatus
SELECT *
FROM a2a_session_tasks
WHERE status = :status_value
ORDER BY priority DESC, created_at ASC;


-- SessionTaskExists
SELECT COUNT(*)
FROM a2a_session_tasks
WHERE id = :id_value;

-- QuerySessionTaskField1
SELECT :field_name_1
FROM a2a_session_tasks
WHERE id = :id_value

-- QuerySessionTaskField2
SELECT :field_name_1, :field_name_2
FROM a2a_session_tasks
WHERE id = :id_value


-- QuerySessionTaskField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM a2a_session_tasks
WHERE id = :id_value


-- QuerySessionTaskField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM a2a_session_tasks
WHERE id = :id_value

-- DeleteSessionTask
DELETE FROM a2a_session_tasks
WHERE id = :id_value;

-- DeleteSessionTasksBySession
DELETE FROM a2a_session_tasks
WHERE session_id = :session_id_value;

-- CheckSessionHasTaskWithStatus
SELECT COUNT(*)
FROM a2a_session_tasks
WHERE session_id = :session_id_value AND status = :status_value;

-- CheckSessionHasTaskWithStatuses
SELECT COUNT(*)
FROM a2a_session_tasks
WHERE session_id = :session_id_value AND status IN (:status_values);

-- GetSessionTaskStatusCounts
SELECT status, COUNT(*) as count
FROM a2a_session_tasks
WHERE session_id = :session_id_value
GROUP BY status;



