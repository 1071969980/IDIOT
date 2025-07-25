
import pytest

from api.vector_db.weaviate.init_impl import (
    _create_data_collection_multi_tenancy,
)

from api.vector_db.weaviate.simple_text import (
    SimpleTextObeject_Weaviate,
    SimpleTextVectorDB_Weaviate,
    SIMPLE_TEXT_OBEJECT_SCHEMA,
)


class TestSimpleTextVectorDBWeaviate:
    """Test cases for SimpleTextVectorDB_Weaviate class"""

    @pytest.fixture
    def db_instance(self):
        """Create a SimpleTextVectorDB_Weaviate instance for testing"""
        return SimpleTextVectorDB_Weaviate("test_collection", "test_tenant")

    @pytest.fixture
    def sample_object(self):
        """Create a sample SimpleTextObeject_Weaviate for testing"""
        return SimpleTextObeject_Weaviate(
            text="Test text",
            collection_name="test_collection",
            tenant_name="test_tenant",
            vector=[0.1, 0.2, 0.3],
        )

    @pytest.fixture
    def sample_objects(self):
        """Create sample SimpleTextObeject_Weaviate list for testing"""
        return [
            SimpleTextObeject_Weaviate(
                text="Test text 1",
                collection_name="test_collection",
                tenant_name="test_tenant",
                vector=[0.1, 0.2, 0.3],
            ),
            SimpleTextObeject_Weaviate(
                text="Test text 2",
                collection_name="test_collection",
                tenant_name="test_tenant",
                vector=[0.4, 0.5, 0.6],
            ),
        ]

    def test_init(self, db_instance: SimpleTextVectorDB_Weaviate) -> None:
        """Test initialization of SimpleTextVectorDB_Weaviate"""
        assert db_instance.collection_name == "test_collection"
        assert db_instance.tenant_name == "test_tenant"
        try:
            _create_data_collection_multi_tenancy(
                collection_name=db_instance.collection_name,
                tenant_name=db_instance.tenant_name,
                properties=SIMPLE_TEXT_OBEJECT_SCHEMA,
            )
        except RuntimeError as e:
            if e.args[0] == f"Collection {db_instance.collection_name} and \
                tenant {db_instance.tenant_name} already exists":
                pass
            else:
                raise
        

    def test_add_object_success(self, db_instance: SimpleTextVectorDB_Weaviate,
                                sample_object: SimpleTextObeject_Weaviate) -> None:
        """Test successful addition of a single object"""
        # Execute
        db_instance.add_object(sample_object)
        
        # Since we're not using mocks, we can't verify the internal calls
        # But we can check that no exception was raised

    def test_add_object_without_vector_raises_error(self, db_instance: SimpleTextVectorDB_Weaviate) -> None:
        """Test that adding object without vector raises ValueError"""
        # Setup
        obj_without_vector = SimpleTextObeject_Weaviate(
            text="Test text",
            collection_name="test_collection",
            tenant_name="test_tenant",
            vector=None,
        )

        # Execute & Verify
        with pytest.raises(ValueError, match="Vector is required"):
            db_instance.add_object(obj_without_vector)

    def test_add_objects_success(self, db_instance: SimpleTextVectorDB_Weaviate,
                                 sample_objects: list[SimpleTextObeject_Weaviate]) -> None:
        """Test successful addition of multiple objects"""
        # Execute
        db_instance.add_objects(sample_objects)
        
        # Since we're not using mocks, we can't verify the internal calls
        # But we can check that no exception was raised

    def test_add_objects_different_collection_raises_error(self, db_instance: SimpleTextVectorDB_Weaviate,
                                                          sample_objects: list[SimpleTextObeject_Weaviate]) -> None:
        """Test that adding objects with different collections raises ValueError"""
        # Setup
        sample_objects[1].collection_name = "different_collection"

        # Execute & Verify
        with pytest.raises(ValueError, match="All objs must have the same collection name"):
            db_instance.add_objects(sample_objects)

    def test_add_objects_different_tenant_raises_error(self, db_instance: SimpleTextVectorDB_Weaviate,
                                                      sample_objects: list[SimpleTextObeject_Weaviate]) -> None:
        """Test that adding objects with different tenants raises ValueError"""
        # Setup
        sample_objects[1].tenant_name = "different_tenant"

        # Execute & Verify
        with pytest.raises(ValueError, match="All objs must have the same tenant name"):
            db_instance.add_objects(sample_objects)

    def test_add_objects_without_vector_raises_error(self, db_instance: SimpleTextVectorDB_Weaviate,
                                                    sample_objects: list[SimpleTextObeject_Weaviate]) -> None:
        """Test that adding objects without vector raises ValueError"""
        # Setup
        sample_objects[1].vector = None

        # Execute & Verify
        with pytest.raises(ValueError, match="All objs must have the vector"):
            db_instance.add_objects(sample_objects)

    def test_id_exists(self, db_instance: SimpleTextVectorDB_Weaviate) -> None:
        """Test checking if ID exists"""
        # Execute
        result = db_instance.id_exists("nonexistent_id")
        
        # Verify
        assert result is False

    def test_delete_by_ids(self, db_instance: SimpleTextVectorDB_Weaviate) -> None:
        """Test deletion by IDs"""
        # Execute
        db_instance.delete_by_ids(["id1", "id2"])
        
        # Since we're not using mocks, we can't verify the internal calls
        # But we can check that no exception was raised

    def test_search_ids_by_metadata_field_not_implemented(self, db_instance: SimpleTextVectorDB_Weaviate) -> None:
        """Test that search_ids_by_metadata_field raises NotImplementedError"""
        with pytest.raises(NotImplementedError):
            db_instance.search_ids_by_metadata_field("key", "value")

    def test_delete_by_metadata_field_not_implemented(self, db_instance: SimpleTextVectorDB_Weaviate) -> None:
        """Test that delete_by_metadata_field raises NotImplementedError"""
        with pytest.raises(NotImplementedError):
            db_instance.delete_by_metadata_field("key", "value")

    def test_search_by_text(self, db_instance: SimpleTextVectorDB_Weaviate) -> None:
        """Test search by text functionality"""
        # Execute
        results = db_instance.search_by_text("Test text")

        # Verify
        assert isinstance(results, list)
        assert len(results) == 2

    def test_search_by_vector(self, db_instance: SimpleTextVectorDB_Weaviate) -> None:
        """Test search by vector functionality"""
        # Execute
        results = db_instance.search_by_vector([0.1, 0.2, 0.3])

        # Verify
        assert isinstance(results, list)
        # Results might be empty since we haven't added any objects

    def test_context_manager_enter_exit(self, db_instance: SimpleTextVectorDB_Weaviate) -> None:
        """Test context manager functionality"""
        # Execute
        with db_instance as collection:
            # Just verify that we can enter and exit the context
            # Without mocks, we can't verify the exact type of collection
            assert collection is not None
