-- CreateU2ASessionStorageTable
CREATE TABLE IF NOT EXISTS u2a_session_storage (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL UNIQUE,
    storage JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE
);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_storage_session_id ON u2a_session_storage (session_id);

-- InsertSessionStorage
INSERT INTO u2a_session_storage (session_id, storage)
VALUES (:session_id, :storage)
RETURNING id;

-- UpdateSessionStorageById
UPDATE u2a_session_storage
SET storage = :storage, updated_at = CURRENT_TIMESTAMP
WHERE id = :id_value;

-- UpdateSessionStorageBySessionId
INSERT INTO u2a_session_storage (session_id, storage)
VALUES (:session_id_value, :storage)
ON CONFLICT (session_id)
DO UPDATE SET
    storage = EXCLUDED.storage,
    updated_at = CURRENT_TIMESTAMP;

-- QuerySessionStorageById
SELECT * FROM u2a_session_storage
WHERE id = :id_value;

-- QuerySessionStorageBySessionId
SELECT * FROM u2a_session_storage
WHERE session_id = :session_id_value;

-- DeleteSessionStorageById
DELETE FROM u2a_session_storage
WHERE id = :id_value;

-- DeleteSessionStorageBySessionId
DELETE FROM u2a_session_storage
WHERE session_id = :session_id_value;

-- SessionStorageExistsById
SELECT EXISTS (
    SELECT 1 FROM u2a_session_storage
    WHERE id = :id_value
);

-- SessionStorageExistsBySessionId
SELECT EXISTS (
    SELECT 1 FROM u2a_session_storage
    WHERE session_id = :session_id_value
);
