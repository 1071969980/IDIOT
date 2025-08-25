from typing import List, Union, Optional, Tuple
from cypher_node import CypherNode
from cypher_edge import CypherEdge


class CypherPattern:
    """
    Represents a fixed-length pattern in Cypher queries.
    
    A pattern consists of alternating nodes and edges, starting and ending with a node.
    Valid patterns:
    - (node)
    - (node)-[edge]->(node)
    - (node)-[edge]->(node)-[edge]->(node)
    - (node)<-[edge]-(node)-[edge]->(node)
    
    Invalid patterns:
    - [edge]  # Must start with node
    - (node)-[edge]  # Must end with node
    - (node)-[edge]-(node)-[edge]  # Must end with node
    """
    
    def __init__(self, elements: Optional[List[Union[CypherNode, CypherEdge]]] = None, 
                 min_length: Optional[int] = None, max_length: Optional[int] = None):
        """
        Initialize a Cypher pattern.
        
        Args:
            elements: List of alternating nodes and edges, must start and end with nodes
            min_length: Minimum repetitions for variable-length patterns
            max_length: Maximum repetitions for variable-length patterns
        """
        self.elements = elements or []
        self.min_length = min_length
        self.max_length = max_length
        self._validate_pattern()
    
    def add_node(self, node: CypherNode) -> 'CypherPattern':
        """Add a node to the pattern."""
        if self.elements and isinstance(self.elements[-1], CypherNode):
            raise ValueError("Cannot add node after another node. Add an edge first.")
        self.elements.append(node)
        return self
    
    def add_edge(self, edge: CypherEdge) -> 'CypherPattern':
        """Add an edge to the pattern."""
        if not self.elements:
            raise ValueError("Cannot add edge as first element. Start with a node.")
        if isinstance(self.elements[-1], CypherEdge):
            raise ValueError("Cannot add edge after another edge. Add a node first.")
        self.elements.append(edge)
        return self
    
    def add_elements(self, *elements: Union[CypherNode, CypherEdge]) -> 'CypherPattern':
        """Add multiple elements in sequence."""
        for element in elements:
            if isinstance(element, CypherNode):
                self.add_node(element)
            elif isinstance(element, CypherEdge):
                self.add_edge(element)
            else:
                raise TypeError("Elements must be either CypherNode or CypherEdge")
        return self
    
    def clear(self) -> 'CypherPattern':
        """Clear all elements from the pattern."""
        self.elements.clear()
        return self
    
    def get_nodes(self) -> List[CypherNode]:
        """Get all nodes in the pattern."""
        return [elem for elem in self.elements if isinstance(elem, CypherNode)]
    
    def get_edges(self) -> List[CypherEdge]:
        """Get all edges in the pattern."""
        return [elem for elem in self.elements if isinstance(elem, CypherEdge)]
    
    def get_length(self) -> int:
        """Get the number of edges in the pattern (path length)."""
        return len(self.get_edges())
    
    def is_variable_length(self) -> bool:
        """Check if this is a variable-length pattern."""
        return self.min_length is not None
    
    def set_variable_length(self, min_length: int, max_length: Optional[int] = None) -> 'CypherPattern':
        """
        Set variable-length quantifier for this pattern.
        
        Args:
            min_length: Minimum number of repetitions
            max_length: Maximum number of repetitions (defaults to min_length if None)
        """
        if min_length < 1:
            raise ValueError("Minimum length must be at least 1")
        
        self.min_length = min_length
        self.max_length = max_length if max_length is not None else min_length
        
        if self.max_length < self.min_length:
            raise ValueError("Maximum length must be greater than or equal to minimum length")
        
        return self
    
    def expand_to_fixed_patterns(self) -> List['CypherPattern']:
        """
        Expand a variable-length pattern into a list of fixed-length patterns.
        
        Returns:
            List of CypherPattern objects representing each possible length
        """
        if not self.is_variable_length():
            return [self]
        
        patterns = []
        base_nodes = self.get_nodes()
        base_edges = self.get_edges()
        
        # For each possible length, create a repeated pattern
        for length in range(self.min_length, self.max_length + 1):
            expanded_elements = []
            
            # First node
            expanded_elements.append(base_nodes[0])
            
            # Repeat the pattern for the specified length
            for i in range(length):
                # Add edges and subsequent nodes
                expanded_elements.extend(base_edges)
                expanded_elements.extend(base_nodes[1:])
            
            patterns.append(CypherPattern(expanded_elements))
        
        return patterns
    
    def _validate_pattern(self) -> None:
        """Validate that the pattern has correct node-edge sequence."""
        if not self.elements:
            return
        
        # Must start and end with a node
        if not isinstance(self.elements[0], CypherNode):
            raise ValueError("Pattern must start with a node")
        if not isinstance(self.elements[-1], CypherNode):
            raise ValueError("Pattern must end with a node")
        
        # Check alternating pattern
        for i, elem in enumerate(self.elements):
            if i % 2 == 0:  # Even indices should be nodes
                if not isinstance(elem, CypherNode):
                    raise ValueError(f"Position {i} should be a node, got edge")
            else:  # Odd indices should be edges
                if not isinstance(elem, CypherEdge):
                    raise ValueError(f"Position {i} should be an edge, got node")
        
        # Validate variable-length parameters
        if self.min_length is not None:
            if self.min_length < 1:
                raise ValueError("Minimum length must be at least 1")
            if self.max_length is not None and self.max_length < self.min_length:
                raise ValueError("Maximum length must be greater than or equal to minimum length")
    
    def __str__(self) -> str:
        """Convert the pattern to Cypher string representation."""
        pattern_str = "".join(str(elem) for elem in self.elements)
        
        # Add variable-length quantifier if present
        if self.is_variable_length():
            if self.min_length == self.max_length:
                return f"({pattern_str}){{{self.min_length}}}"
            else:
                return f"({pattern_str}){{{self.min_length},{self.max_length}}}"
        else:
            return pattern_str
    
    def __repr__(self) -> str:
        """Return a string representation of the object."""
        if self.is_variable_length():
            return f"CypherPattern(elements={len(self.elements)}, nodes={len(self.get_nodes())}, edges={len(self.get_edges())}, variable_length=({self.min_length},{self.max_length}))"
        else:
            return f"CypherPattern(elements={len(self.elements)}, nodes={len(self.get_nodes())}, edges={len(self.get_edges())})"
    
    @classmethod
    def from_nodes_and_edges(
        cls, 
        nodes: List[CypherNode], 
        edges: List[CypherEdge]
    ) -> 'CypherPattern':
        """
        Create a pattern from separate lists of nodes and edges.
        
        Args:
            nodes: List of nodes (must have one more node than edges)
            edges: List of edges (must have one less edge than nodes)
        """
        if len(nodes) != len(edges) + 1:
            raise ValueError(f"Pattern must have exactly one more node than edges. Got {len(nodes)} nodes and {len(edges)} edges")
        
        elements = []
        for i in range(len(nodes)):
            elements.append(nodes[i])
            if i < len(edges):
                elements.append(edges[i])
        
        return cls(elements)
    
    @classmethod
    def create_variable_length(
        cls,
        base_elements: List[Union[CypherNode, CypherEdge]],
        min_length: int,
        max_length: Optional[int] = None
    ) -> 'CypherPattern':
        """
        Create a variable-length pattern.
        
        Args:
            base_elements: Elements of the base pattern to be repeated
            min_length: Minimum number of repetitions
            max_length: Maximum number of repetitions (defaults to min_length if None)
        """
        pattern = cls(base_elements)
        pattern.set_variable_length(min_length, max_length)
        return pattern