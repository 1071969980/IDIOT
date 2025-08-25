#!/usr/bin/env python3
"""
Test script for CypherPattern class.
"""

import sys
import os

# Add the current directory to the path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cypher_pattern import CypherPattern
from cypher_node import CypherNode
from cypher_edge import CypherEdge


def test_single_node():
    """Test pattern with a single node."""
    print("=== Single Node Pattern ===")
    
    node = CypherNode(variable="n", labels=["Person"])
    pattern = CypherPattern([node])
    print(f"Single node: {pattern}")
    print(f"Length: {pattern.get_length()}")
    print()


def test_two_node_pattern():
    """Test pattern with two nodes and one edge."""
    print("=== Two Node Pattern ===")
    
    person1 = CypherNode(variable="p1", labels=["Person"], properties={"name": "Alice"})
    person2 = CypherNode(variable="p2", labels=["Person"], properties={"name": "Bob"})
    knows = CypherEdge(variable="k", type="KNOWS", direction="left_right")
    
    pattern = CypherPattern([person1, knows, person2])
    print(f"Two nodes: {pattern}")
    print(f"Length: {pattern.get_length()}")


def test_three_node_pattern():
    """Test pattern with three nodes and two edges."""
    print("=== Three Node Pattern ===")
    
    alice = CypherNode(variable="a", labels=["Person"], properties={"name": "Alice"})
    company = CypherNode(variable="c", labels=["Company"], properties={"name": "TechCorp"})
    bob = CypherNode(variable="b", labels=["Person"], properties={"name": "Bob"})
    
    works_at = CypherEdge(type="WORKS_AT", direction="left_right")
    knows = CypherEdge(type="KNOWS", direction="right_left")
    
    pattern = CypherPattern([alice, works_at, company, knows, bob])
    print(f"Three nodes: {pattern}")
    print(f"Length: {pattern.get_length()}")
    print()


def test_method_chaining():
    """Test building pattern using method chaining."""
    print("=== Method Chaining ===")
    
    pattern = (CypherPattern()
               .add_node(CypherNode(variable="a", labels=["Person"]))
               .add_edge(CypherEdge(type="LIKES"))
               .add_node(CypherNode(variable="b", labels=["Person"], properties={"name": "Bob"})))
    
    print(f"Chained pattern: {pattern}")
    print()


def test_from_nodes_and_edges():
    """Test creating pattern from separate lists."""
    print("=== From Nodes and Edges Lists ===")
    
    nodes = [
        CypherNode(variable="s", labels=["Student"]),
        CypherNode(variable="t", labels=["Teacher"]),
        CypherNode(variable="c", labels=["Course"])
    ]
    
    edges = [
        CypherEdge(type="STUDIES_WITH"),
        CypherEdge(type="TEACHES", direction="right_left")
    ]
    
    pattern = CypherPattern.from_nodes_and_edges(nodes, edges)
    print(f"From lists: {pattern}")
    print()


def test_complex_pattern():
    """Test a more complex pattern with mixed directions."""
    print("=== Complex Pattern ===")
    
    # Create a pattern: (Alice)<-[:WORKS_AT]-(TechCorp)-[:LOCATED_IN]->(City)
    alice = CypherNode(labels=["Person"], properties={"name": "Alice"})
    techcorp = CypherNode(labels=["Company"], properties={"name": "TechCorp"})
    city = CypherNode(labels=["City"], properties={"name": "San Francisco"})
    
    works_at = CypherEdge(type="WORKS_AT", direction="right_left")
    located_in = CypherEdge(type="LOCATED_IN", direction="left_right")
    
    pattern = CypherPattern([alice, works_at, techcorp, located_in, city])
    print(f"Complex: {pattern}")
    print()


def test_validation_errors():
    """Test validation errors."""
    print("=== Validation Errors ===")
    
    try:
        # Invalid: starting with edge
        edge = CypherEdge(type="KNOWS")
        CypherPattern([edge])
    except ValueError as e:
        print(f"Error (start with edge): {e}")
    
    try:
        # Invalid: ending with edge
        node = CypherNode()
        pattern = CypherPattern([node])
        pattern.add_edge(CypherEdge())
    except ValueError as e:
        print(f"Error (end with edge): {e}")
    
    try:
        # Invalid: two nodes in a row
        node1 = CypherNode()
        node2 = CypherNode()
        CypherPattern([node1, node2])
    except ValueError as e:
        print(f"Error (two nodes): {e}")
    
    try:
        # Invalid: from_nodes_and_edges with wrong counts
        nodes = [CypherNode(), CypherNode()]
        edges = [CypherEdge(), CypherEdge()]
        CypherPattern.from_nodes_and_edges(nodes, edges)
    except ValueError as e:
        print(f"Error (wrong counts): {e}")
    
    print()


def test_helper_methods():
    """Test helper methods."""
    print("=== Helper Methods ===")
    
    alice = CypherNode(variable="a", labels=["Person"])
    bob = CypherNode(variable="b", labels=["Person"])
    charlie = CypherNode(variable="c", labels=["Person"])
    
    likes1 = CypherEdge(type="LIKES")
    likes2 = CypherEdge(type="LIKES")
    
    pattern = CypherPattern([alice, likes1, bob, likes2, charlie])
    
    print(f"Pattern: {pattern}")
    print(f"Nodes: {len(pattern.get_nodes())}")
    print(f"Edges: {len(pattern.get_edges())}")
    print(f"Length: {pattern.get_length()}")
    print()


def test_variable_length_pattern():
    """Test variable-length pattern functionality."""
    print("=== Variable-Length Pattern ===")
    
    # Create base pattern: (:Person)-[:FRIEND]->(:Person)
    person1 = CypherNode(labels=["Person"])
    person2 = CypherNode(labels=["Person"])
    friend_edge = CypherEdge(type="FRIEND", direction="left_right")
    
    # Test 1: Create variable-length pattern with range {1,5}
    print("1. Variable-length pattern with range {1,5}:")
    var_pattern = CypherPattern([person1, friend_edge, person2])
    var_pattern.set_variable_length(1, 5)
    print(f"Pattern: {var_pattern}")
    print(f"Is variable length: {var_pattern.is_variable_length()}")
    print(f"Min length: {var_pattern.min_length}")
    print(f"Max length: {var_pattern.max_length}")
    print()
    
    # Test 2: Create variable-length pattern with exact length {3}
    print("2. Variable-length pattern with exact length {3}:")
    exact_pattern = CypherPattern.create_variable_length(
        [person1, friend_edge, person2], 3
    )
    print(f"Pattern: {exact_pattern}")
    print()
    
    # Test 3: Expand variable-length pattern to fixed patterns
    print("3. Expanding variable-length pattern {1,3}:")
    expand_pattern = CypherPattern([person1, friend_edge, person2])
    expand_pattern.set_variable_length(1, 3)
    expanded_patterns = expand_pattern.expand_to_fixed_patterns()
    
    for i, pattern in enumerate(expanded_patterns):
        print(f"  Length {i+1}: {pattern}")
        print(f"    Nodes: {len(pattern.get_nodes())}, Edges: {len(pattern.get_edges())}")
    print()
    
    # Test 4: Fixed-length pattern (for comparison)
    print("4. Fixed-length pattern (for comparison):")
    fixed_pattern = CypherPattern([person1, friend_edge, person2])
    print(f"Pattern: {fixed_pattern}")
    print(f"Is variable length: {fixed_pattern.is_variable_length()}")
    print()
    
    # Test 5: Error cases
    print("5. Testing error cases:")
    try:
        error_pattern = CypherPattern([person1, friend_edge, person2])
        error_pattern.set_variable_length(0, 5)  # Should fail
    except ValueError as e:
        print(f"  Expected error (min < 1): {e}")
    
    try:
        error_pattern = CypherPattern([person1, friend_edge, person2])
        error_pattern.set_variable_length(5, 3)  # Should fail
    except ValueError as e:
        print(f"  Expected error (max < min): {e}")
    print()


def main():
    """Run all tests."""
    print("Testing CypherPattern class\n")
    
    test_single_node()
    test_two_node_pattern()
    test_three_node_pattern()
    test_method_chaining()
    test_from_nodes_and_edges()
    test_complex_pattern()
    test_validation_errors()
    test_helper_methods()
    test_variable_length_pattern()
    
    print("All tests completed!")


if __name__ == "__main__":
    main()