#!/usr/bin/env python3
"""
Test script for CypherEdge class.
"""

import sys
import os

# Add the current directory to the path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cypher_edge import CypherEdge
from cypher_node import CypherNode


def test_edge_basic():
    """Test basic edge functionality."""
    print("=== Basic Edge Tests ===")
    
    # Test 1: Simple undirected edge
    edge1 = CypherEdge()
    print(f"Empty edge: {edge1}")
    
    # Test 2: Edge with variable
    edge2 = CypherEdge(variable="r")
    print(f"Edge with variable: {edge2}")
    
    # Test 3: Edge with type
    edge3 = CypherEdge(type="KNOWS")
    print(f"Edge with type: {edge3}")
    
    # Test 4: Edge with variable and type
    edge4 = CypherEdge(variable="r", type="FRIENDS")
    print(f"Edge with variable and type: {edge4}")
    
    print()


def test_edge_directions():
    """Test different edge directions."""
    print("=== Edge Direction Tests ===")
    
    # Test different directions
    base_edge = CypherEdge(variable="r", type="KNOWS")
    
    print(f"Left to right: {base_edge}")
    
    base_edge.set_direction("right_left")
    print(f"Right to left: {base_edge}")
    
    base_edge.set_direction("undirected")
    print(f"Undirected: {base_edge}")
    
    print()


def test_edge_properties():
    """Test edge with properties."""
    print("=== Edge Properties Tests ===")
    
    # Edge with properties
    edge = CypherEdge(
        variable="r",
        type="FRIENDS",
        properties={"since": 2020, "close": True}
    )
    print(f"Edge with properties: {edge}")
    
    # Add more properties
    edge.set_property("meeting_place", "school")
    print(f"Edge after adding property: {edge}")
    
    # Remove a property
    edge.remove_property("close")
    print(f"Edge after removing property: {edge}")
    
    print()


def test_method_chaining():
    """Test method chaining."""
    print("=== Method Chaining Tests ===")
    
    edge = (CypherEdge()
            .set_variable("e")
            .set_type("WORKS_AT")
            .set_property("role", "Engineer")
            .set_property("since", 2021)
            .set_direction("left_right"))
    
    print(f"Chained edge creation: {edge}")
    
    print()


def test_path_example():
    """Test creating a complete path."""
    print("=== Complete Path Example ===")
    
    # Create nodes
    alice = CypherNode(variable="a", labels=["Person"], properties={"name": "Alice"})
    bob = CypherNode(variable="b", labels=["Person"], properties={"name": "Bob"})
    
    # Create edge
    friendship = CypherEdge(
        variable="f",
        type="FRIENDS",
        properties={"since": 2020},
        direction="left_right"
    )
    
    # Combine them
    path = f"{alice}{friendship}{bob}"
    print(f"Complete path: {path}")
    
    # Another example with different direction
    works_at = CypherEdge(
        variable="w",
        type="WORKS_AT",
        properties={"role": "Developer"},
        direction="right_left"
    )
    
    company = CypherNode(variable="c", labels=["Company"], properties={"name": "TechCorp"})
    path2 = f"{bob}{works_at}{company}"
    print(f"Another path: {path2}")
    
    print()


def main():
    """Run all tests."""
    print("Testing CypherEdge class\n")
    
    test_edge_basic()
    test_edge_directions()
    test_edge_properties()
    test_method_chaining()
    test_path_example()
    
    print("All tests completed!")


if __name__ == "__main__":
    main()