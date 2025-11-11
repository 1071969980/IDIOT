-- CreateTable
CREATE TABLE IF NOT EXISTS a2a_sessions (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_a_id UUID NOT NULL,
    user_b_id UUID NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_a_id) REFERENCES simple_users(id) ON DELETE CASCADE,
    FOREIGN KEY (user_b_id) REFERENCES simple_users(id) ON DELETE CASCADE
);
--
CREATE INDEX IF NOT EXISTS idx_a2a_sessions_user_a_id ON a2a_sessions (user_a_id);
--
CREATE INDEX IF NOT EXISTS idx_a2a_sessions_user_b_id ON a2a_sessions (user_b_id);

-- InsertSession
INSERT INTO a2a_sessions (user_a_id, user_b_id)
VALUES (:user_a_id, :user_b_id)
RETURNING id;

-- UpdateSession1
UPDATE a2a_sessions
SET :field_name_1 = :field_value_1
WHERE id = :id_value;

-- UpdateSession2
UPDATE a2a_sessions
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE id = :id_value;

-- UpdateSession3
UPDATE a2a_sessions
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE id = :id_value;

-- QuerySession
SELECT *
FROM a2a_sessions
WHERE id = :id_value;

-- QuerySessionByUserAId
SELECT *
FROM a2a_sessions
WHERE user_a_id = :user_a_id_value;

-- QuerySessionByUserBId
SELECT *
FROM a2a_sessions
WHERE user_b_id = :user_b_id_value;

-- QuerySessionsByUserId
SELECT *
FROM a2a_sessions
WHERE user_a_id = :user_id_value OR user_b_id = :user_id_value;

-- IsExists
SELECT COUNT(*)
FROM a2a_sessions
WHERE id = :id_value;

-- QueryField1
SELECT :field_name_1
FROM a2a_sessions
WHERE id = :id_value;

-- QueryField2
SELECT :field_name_1, :field_name_2
FROM a2a_sessions
WHERE id = :id_value;

-- QueryField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM a2a_sessions
WHERE id = :id_value;

-- QueryField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM a2a_sessions
WHERE id = :id_value;

-- QueryField5
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4, :field_name_5
FROM a2a_sessions
WHERE id = :id_value;

-- DeleteSession
DELETE FROM a2a_sessions
WHERE id = :id_value;

