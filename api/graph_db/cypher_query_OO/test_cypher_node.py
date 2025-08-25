from cypher_node import CypherNode

# Example usage
if __name__ == "__main__":
    # Simple node with variable
    node1 = CypherNode(variable="n")
    print(node1)  # (n)
    
    # Node with label
    node2 = CypherNode(labels="Person")
    print(node2)  # (:Person)
    
    # Node with variable and label
    node3 = CypherNode(variable="p", labels="Person")
    print(node3)  # (p:Person)
    
    # Node with properties
    node4 = CypherNode(
        variable="a",
        labels=["Person", "User"],
        properties={"name": "Alice", "age": 30, "active": True}
    )
    print(node4)  # (a:Person:User {name: 'Alice', age: 30, active: True})
    
    # Node with only properties
    node5 = CypherNode(properties={"id": 123})
    print(node5)  # ({id: 123})
    
    # Using method chaining
    node6 = CypherNode().set_variable("n").add_label("Employee").set_property("name", "Bob")
    print(node6)  # (n:Employee {name: 'Bob'})