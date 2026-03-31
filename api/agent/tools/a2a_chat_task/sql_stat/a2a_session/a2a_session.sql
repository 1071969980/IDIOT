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

-- DeleteSession
DELETE FROM a2a_sessions
WHERE id = :id_value;

