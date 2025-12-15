-- CreateFileSystemTable
CREATE TABLE IF NOT EXISTS user_file_system (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_id UUID NOT NULL,
    file_path TEXT NOT NULL,
    item_type TEXT NOT NULL CHECK (item_type IN ('file', 'folder')),
    is_encrypted BOOLEAN DEFAULT FALSE,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES simple_users(id) ON DELETE CASCADE
);
--
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_file_system_user_path ON user_file_system (user_id, file_path);
--
CREATE INDEX IF NOT EXISTS idx_user_file_system_user_id ON user_file_system (user_id);
--
CREATE INDEX IF NOT EXISTS idx_user_file_system_item_type ON user_file_system (item_type);
--
CREATE INDEX IF NOT EXISTS idx_user_file_system_is_encrypted ON user_file_system (is_encrypted);


-- InsertFileSystemItem
INSERT INTO user_file_system (user_id, file_path, item_type, is_encrypted, metadata)
VALUES (:user_id, :file_path, :item_type, :is_encrypted, :metadata)
RETURNING id;

-- QueryFileSystemItemById
SELECT * FROM user_file_system WHERE id = :id_value;

-- QueryFileSystemItemsByUser
SELECT * FROM user_file_system WHERE user_id = :user_id_value ORDER BY file_path;

-- QueryFileSystemItemsByPath
SELECT * FROM user_file_system WHERE user_id = :user_id_value AND file_path = :file_path_value;

-- QueryFileSystemItemsByType
SELECT * FROM user_file_system WHERE user_id = :user_id_value AND item_type = :item_type_value ORDER BY file_path;

-- QueryFileSystemItemsByParentPath
SELECT * FROM user_file_system
WHERE user_id = :user_id_value
AND file_path LIKE :parent_path_pattern ESCAPE "\"
ORDER BY file_path;

-- QueryFileSystemItemsByParentPathWithDepth
SELECT * FROM user_file_system
WHERE user_id = :user_id_value
AND file_path LIKE :parent_path_pattern ESCAPE "\"
AND (
    :max_depth IS NULL
    OR array_length(string_to_array(file_path, '/'), 1) - array_length(string_to_array(:parent_path_clean, '/'), 1) <= :max_depth
)
ORDER BY file_path;

-- UpdateFileSystemItem
UPDATE user_file_system
SET file_path = :file_path_value,
    item_type = :item_type_value,
    is_encrypted = :is_encrypted_value,
    metadata = :metadata_value
WHERE id = :id_value;

-- UpdateFileSystemItemPath
UPDATE user_file_system
SET file_path = :new_file_path_value
WHERE id = :id_value;

-- UpdateFileSystemItemEncryption
UPDATE user_file_system
SET is_encrypted = :is_encrypted_value
WHERE id = :id_value;

-- DeleteFileSystemItemById
DELETE FROM user_file_system WHERE id = :id_value;

-- DeleteFileSystemItemsByUser
DELETE FROM user_file_system WHERE user_id = :user_id_value;

-- DeleteFileSystemItemsByPath
DELETE FROM user_file_system WHERE user_id = :user_id_value AND file_path = :file_path_value;

-- DeleteFileSystemItemsByParentPath
DELETE FROM user_file_system
WHERE user_id = :user_id_value
AND file_path LIKE :parent_path_pattern ESCAPE "\";

-- InsertFileSystemItemsBatch
INSERT INTO user_file_system (user_id, file_path, item_type, is_encrypted, metadata)
SELECT
    unnest(:user_ids_list) as user_id,
    unnest(:file_paths_list) as file_path,
    unnest(:item_types_list) as item_type,
    unnest(:is_encrypted_list) as is_encrypted,
    unnest(:metadata_list) as metadata
RETURNING id;

-- UpdateFileSystemItemsStatus
UPDATE user_file_system
SET is_encrypted = :is_encrypted_value
WHERE id = ANY(:ids_list);

-- QueryFileSystemItemsByIds
SELECT * FROM user_file_system WHERE id = ANY(:ids_list) ORDER BY file_path;

-- CreateFileSystemTriggers
CREATE OR REPLACE FUNCTION user_file_system_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE TRIGGER user_file_system_before_update
BEFORE UPDATE ON user_file_system
FOR EACH ROW
EXECUTE FUNCTION user_file_system_update_timestamp();