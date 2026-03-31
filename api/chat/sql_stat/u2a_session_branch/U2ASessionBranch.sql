-- CreateSessionBranchesTable
CREATE EXTENSION IF NOT EXISTS ltree;
--
CREATE TABLE IF NOT EXISTS u2a_session_branches (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_by VARCHAR(32) NOT NULL CHECK (created_by IN ('user', 'agent', 'system')),
    archived BOOLEAN DEFAULT FALSE,
    leaf_task_id UUID NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE,
    UNIQUE (session_id, name)
);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_branches_session_id ON u2a_session_branches (session_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_branches_leaf_task_id ON u2a_session_branches (leaf_task_id);

-- CreateSessionBranchTriggers
CREATE OR REPLACE FUNCTION u2a_session_branch_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE TRIGGER u2a_session_branch_before_insert
BEFORE INSERT ON u2a_session_branches
FOR EACH ROW
EXECUTE FUNCTION u2a_session_branch_update_timestamp();
--
CREATE OR REPLACE TRIGGER u2a_session_branch_before_update
BEFORE UPDATE ON u2a_session_branches
FOR EACH ROW
EXECUTE FUNCTION u2a_session_branch_update_timestamp();

-- InsertSessionBranch
INSERT INTO u2a_session_branches (session_id, name, created_by, leaf_task_id)
VALUES (:session_id, :name, :created_by, :leaf_task_id)
RETURNING id;

-- QuerySessionBranchById
SELECT *
FROM u2a_session_branches
WHERE id = :id_value;

-- QuerySessionBranchBySessionAndName
SELECT *
FROM u2a_session_branches
WHERE session_id = :session_id_value AND name = :name_value;

-- QuerySessionBranchesBySession
SELECT *
FROM u2a_session_branches
WHERE session_id = :session_id_value
ORDER BY created_at;

-- QuerySessionBranchByLeafTaskId
SELECT *
FROM u2a_session_branches
WHERE leaf_task_id = :leaf_task_id_value;

-- SessionBranchExists
SELECT COUNT(*)
FROM u2a_session_branches
WHERE id = :id_value;

-- UpdateSessionBranchLeafTask
UPDATE u2a_session_branches
SET leaf_task_id = :leaf_task_id_value
WHERE id = :id_value;

-- UpdateSessionBranchArchived
UPDATE u2a_session_branches
SET archived = :archived_value
WHERE id = :id_value;

-- DeleteSessionBranch
DELETE FROM u2a_session_branches
WHERE id = :id_value;

-- DeleteSessionBranchesBySession
DELETE FROM u2a_session_branches
WHERE session_id = :session_id_value;
