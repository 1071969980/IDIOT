from typing import Dict, Any, Optional, List, Union


class CypherNode:
    """
    Represents a node element in Cypher queries.
    
    Examples:
        (n)
        (n:Person)
        (n:Person {name: 'Alice', age: 30})
        (:Person)
        (:Person {name: 'Alice'})
        ({name: 'Alice'})
    """
    
    def __init__(
        self,
        variable: Optional[str] = None,
        labels: Optional[Union[str, List[str]]] = None,
        properties: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a Cypher node.
        
        Args:
            variable: Variable name for the node (e.g., 'n', 'p')
            labels: Single label string or list of labels (e.g., 'Person' or ['Person', 'User'])
            properties: Dictionary of node properties
        """
        self.variable = variable
        self.labels = labels if isinstance(labels, list) else [labels] if labels else []
        self.properties = properties or {}
    
    def set_variable(self, variable: str) -> 'CypherNode':
        """Set the variable name for the node."""
        self.variable = variable
        return self
    
    def add_label(self, label: str) -> 'CypherNode':
        """Add a label to the node."""
        if label and label not in self.labels:
            self.labels.append(label)
        return self
    
    def set_property(self, key: str, value: Any) -> 'CypherNode':
        """Set a property value."""
        self.properties[key] = value
        return self
    
    def set_properties(self, properties: Dict[str, Any]) -> 'CypherNode':
        """Set multiple properties."""
        self.properties.update(properties)
        return self
    
    def remove_property(self, key: str) -> 'CypherNode':
        """Remove a property."""
        self.properties.pop(key, None)
        return self
    
    def _format_properties(self) -> str:
        """Format properties dictionary to Cypher string."""
        if not self.properties:
            return ""
        
        props = []
        for key, value in self.properties.items():
            if isinstance(value, str):
                props.append(f"{key}: '{value}'")
            elif isinstance(value, (int, float, bool)):
                props.append(f"{key}: {value}")
            elif value is None:
                props.append(f"{key}: null")
            else:
                # For other types, convert to string
                props.append(f"{key}: '{str(value)}'")
        
        return f"{{{', '.join(props)}}}"
    
    def __str__(self) -> str:
        """Convert the node to Cypher string representation."""
        parts = ["("]
        
        # Add variable if present
        if self.variable:
            parts.append(self.variable)
        
        # Add labels if present
        if self.labels:
            for label in self.labels:
                if label:  # Skip empty labels
                    parts.append(f":{label}")
        
        # Add properties if present
        props_str = self._format_properties()
        if props_str:
            # Add space between labels and properties
            if self.labels or self.variable:
                parts.append(" ")
            parts.append(props_str)
        
        parts.append(")")
        return "".join(parts)
    
    def __repr__(self) -> str:
        """Return a string representation of the object."""
        return f"CypherNode(variable='{self.variable}', labels={self.labels}, properties={self.properties})"


class CypherNodeList:
    """
    Represents a list of Cypher nodes that can be formatted as a comma-separated string.
    
    Examples:
        (charlie:Person:Actor {name: 'Charlie Sheen'}), (oliver:Person:Director {name: 'Oliver Stone'})
        (n1), (n2:Person), (n3:User {name: 'Alice'})
    """
    
    def __init__(self, nodes: Optional[List[CypherNode]] = None):
        """
        Initialize a Cypher node list.
        
        Args:
            nodes: List of CypherNode objects
        """
        self.nodes = nodes or []
    
    def add_node(self, node: CypherNode) -> 'CypherNodeList':
        """Add a node to the list."""
        self.nodes.append(node)
        return self
    
    def add_nodes(self, nodes: List[CypherNode]) -> 'CypherNodeList':
        """Add multiple nodes to the list."""
        self.nodes.extend(nodes)
        return self
    
    def remove_node(self, index: int) -> 'CypherNodeList':
        """Remove a node by index."""
        if 0 <= index < len(self.nodes):
            self.nodes.pop(index)
        return self
    
    def clear(self) -> 'CypherNodeList':
        """Clear all nodes from the list."""
        self.nodes.clear()
        return self
    
    def __str__(self) -> str:
        """Convert the node list to Cypher string representation."""
        return ", ".join(str(node) for node in self.nodes)
    
    def __repr__(self) -> str:
        """Return a string representation of the object."""
        return f"CypherNodeList(nodes={self.nodes})"
    
    def __len__(self) -> int:
        """Return the number of nodes in the list."""
        return len(self.nodes)
    
    def __getitem__(self, index: int) -> CypherNode:
        """Get a node by index."""
        return self.nodes[index]
    
    def __setitem__(self, index: int, node: CypherNode) -> None:
        """Set a node by index."""
        self.nodes[index] = node
    
    def __iter__(self):
        """Iterate over nodes."""
        return iter(self.nodes)