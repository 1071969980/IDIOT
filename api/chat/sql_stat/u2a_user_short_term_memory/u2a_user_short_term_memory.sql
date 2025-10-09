-- CreateUserShortTermMemoryTable
CREATE TABLE IF NOT EXISTS u2a_user_short_term_memory (
    id BIGSERIAL PRIMARY KEY,
    user_id CHAR(36) NOT NULL,
    session_id CHAR(36) NOT NULL,
    seq_index INT NOT NULL,
    content JSONB NOT NULL,
    session_task_id CHAR(36),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES simple_users(uuid) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (session_task_id) REFERENCES u2a_session_tasks(task_uuid) ON DELETE SET NULL
);

CREATE INDEX idx_u2a_user_short_term_memory_session_id ON u2a_user_short_term_memory (session_id);
CREATE INDEX idx_u2a_user_short_term_memory_user_id ON u2a_user_short_term_memory (user_id);
CREATE INDEX idx_u2a_user_short_term_memory_session_task_id ON u2a_user_short_term_memory (session_task_id);

-- InsertUserShortTermMemory
INSERT INTO u2a_user_short_term_memory (user_id, session_id, seq_index, content, session_task_id)
VALUES (:user_id, :session_id, :seq_index, :content, :session_task_id);

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
WHERE id IN :ids_list;

-- QueryUserShortTermMemoryById
SELECT *
FROM u2a_user_short_term_memory
WHERE id = :id_value;


-- QueryUserShortTermMemoryBySession
SELECT *
FROM u2a_user_short_term_memory
WHERE session_id = :session_id_value
ORDER BY seq_index;

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

-- GetNextUserShortTermMemorySeqIndex
SELECT COALESCE(MAX(seq_index), -1) + 1 FROM u2a_user_short_term_memory WHERE session_id = :session_id;

