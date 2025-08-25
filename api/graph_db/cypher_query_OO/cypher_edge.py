from typing import Optional, Dict, Any, List, Union


class CypherEdge:
    """
    Represents an edge (relationship) element in Cypher queries.
    
    Examples:
        -[]-
        -[r]->
        <-[r:KNOWS]-
        -[:FRIENDS {since: 2020}]->
        <-[r:WORKS_AT {role: 'Engineer'}]-
    """
    
    def __init__(
        self,
        variable: Optional[str] = None,
        type: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        direction: str = "left_right"
    ):
        """
        Initialize a Cypher edge.
        
        Args:
            variable: Variable name for the edge (e.g., 'r', 'e')
            type: Relationship type (e.g., 'KNOWS', 'FRIENDS', 'WORKS_AT')
            properties: Dictionary of edge properties
            direction: Edge direction, one of:
                      - "left_right": -[r]-> (default)
                      - "right_left": <-[r]-
                      - "undirected": -[r]-
        """
        self.variable = variable
        self.type = type
        self.properties = properties or {}
        self.direction = direction
    
    def set_variable(self, variable: str) -> 'CypherEdge':
        """Set the variable name for the edge."""
        self.variable = variable
        return self
    
    def set_type(self, type: str) -> 'CypherEdge':
        """Set the relationship type."""
        self.type = type
        return self
    
    def set_property(self, key: str, value: Any) -> 'CypherEdge':
        """Set a property value."""
        self.properties[key] = value
        return self
    
    def set_properties(self, properties: Dict[str, Any]) -> 'CypherEdge':
        """Set multiple properties."""
        self.properties.update(properties)
        return self
    
    def remove_property(self, key: str) -> 'CypherEdge':
        """Remove a property."""
        self.properties.pop(key, None)
        return self
    
    def set_direction(self, direction: str) -> 'CypherEdge':
        """Set the edge direction."""
        if direction not in ["left_right", "right_left", "undirected"]:
            raise ValueError("Direction must be one of: 'left_right', 'right_left', 'undirected'")
        self.direction = direction
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
        """Convert the edge to Cypher string representation."""
        # Build the content inside brackets
        content = []
        
        # Add variable if present
        if self.variable:
            content.append(self.variable)
        
        # Add type if present
        if self.type:
            content.append(f":{self.type}")
        
        # Add properties if present
        props_str = self._format_properties()
        if props_str:
            # Add space between variable/type and properties
            if self.variable or self.type:
                content.append(" ")
            content.append(props_str)
        
        # Create the bracket content
        bracket_content = "".join(content)
        
        # Add direction arrows
        if self.direction == "left_right":
            return f"-[{bracket_content}]->"
        elif self.direction == "right_left":
            return f"<-[{bracket_content}]-"
        else:  # undirected
            return f"-[{bracket_content}]-"
    
    def __repr__(self) -> str:
        """Return a string representation of the object."""
        return f"CypherEdge(variable='{self.variable}', type='{self.type}', properties={self.properties}, direction='{self.direction}')"