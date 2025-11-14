-- CreateUserShortTermMemoryTable
CREATE TABLE IF NOT EXISTS u2a_user_short_term_memory (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_id UUID NOT NULL,
    session_id UUID NOT NULL,
    seq_index INT NOT NULL,
    content JSONB NOT NULL,
    session_task_id UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES simple_users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (session_task_id) REFERENCES u2a_session_tasks(id) ON DELETE CASCADE
);
--
CREATE INDEX IF NOT EXISTS idx_u2a_user_short_term_memory_session_id ON u2a_user_short_term_memory (session_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_user_short_term_memory_user_id ON u2a_user_short_term_memory (user_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_user_short_term_memory_session_task_id ON u2a_user_short_term_memory (session_task_id);

-- InsertUserShortTermMemory
INSERT INTO u2a_user_short_term_memory (user_id, session_id, seq_index, content, session_task_id)
VALUES (:user_id, :session_id, :seq_index, :content, :session_task_id)
RETURNING id;

-- InsertUserShortTermMemoriesBatch
INSERT INTO u2a_user_short_term_memory (user_id, session_id, seq_index, content, session_task_id)
SELECT
    unnest(:user_ids_list) as user_id,
    unnest(:session_ids_list) as session_id,
    unnest(:seq_indices_list) as seq_index,
    unnest(:contents_list) as content,
    unnest(:session_task_ids_list) as session_task_id
RETURNING id;

-- UpdateUserShortTermMemory1
UPDATE u2a_user_short_term_memory
SET :field_name_1 = :field_value_1
WHERE id = :id_value;

-- UpdateUserShortTermMemory2
UPDATE u2a_user_short_term_memory
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE id = :id_value;

-- UpdateUserShortTermMemory3
UPDATE u2a_user_short_term_memory
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE id = :id_value;

-- UpdateUserShortTermMemorySessionTaskByIds
UPDATE u2a_user_short_term_memory
SET session_task_id = :session_task_id_value
WHERE id IN (:ids_list);


-- QueryUserShortTermMemoryById
SELECT *
FROM u2a_user_short_term_memory
WHERE id = :id_value;


-- QueryUserShortTermMemoryBySession
SELECT *
FROM u2a_user_short_term_memory
WHERE session_id = :session_id_value
ORDER BY seq_index;

-- QueryUserShortTermMemoryBySessionTask
SELECT *
FROM u2a_user_short_term_memory
WHERE session_task_id = :session_task_id_value;

-- QueryUserShortTermMemoryByUser
SELECT *
FROM u2a_user_short_term_memory
WHERE user_id = :user_id_value
ORDER BY created_at;

-- UserShortTermMemoryExists
SELECT COUNT(*)
FROM u2a_user_short_term_memory
WHERE id = :id_value;


-- QueryUserShortTermMemoryField1
SELECT :field_name_1
FROM u2a_user_short_term_memory
WHERE id = :id_value;

-- QueryUserShortTermMemoryField2
SELECT :field_name_1, :field_name_2
FROM u2a_user_short_term_memory
WHERE id = :id_value;

-- QueryUserShortTermMemoryField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM u2a_user_short_term_memory
WHERE id = :id_value;

-- QueryUserShortTermMemoryField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM u2a_user_short_term_memory
WHERE id = :id_value;

-- DeleteUserShortTermMemory
DELETE FROM u2a_user_short_term_memory
WHERE id = :id_value;


-- DeleteUserShortTermMemoryBySession
DELETE FROM u2a_user_short_term_memory
WHERE session_id = :session_id_value;

-- DeleteUserShortTermMemoryBySessionTask
DELETE FROM u2a_user_short_term_memory
WHERE session_task_id = :session_task_id_value;

-- GetNextUserShortTermMemorySeqIndex
SELECT COALESCE(MAX(seq_index), -1) + 1 FROM u2a_user_short_term_memory WHERE session_id = :session_id;

