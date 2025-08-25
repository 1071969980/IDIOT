import asyncio
import neo4j
from typing import List, Tuple, Iterable
from api.graph_db.cypher_query_OO import CypherNode, CypherNodeList, CypherEdge, CypherPattern
from .execption import CypherNodeUnexpectedGraphException, CypherNodeUnexpectedTenantException

def _try_add_tenant_lable_to_node(node: CypherNode, tenant: str) -> CypherNode:
    tenant_label = f"TENANT_{tenant}"
    for label in node.labels:
        if label.startswith("TENANT"):
            if label != tenant_label:
                msg = f"Node {node.variable} already has a tenant label {label}"
                raise CypherNodeUnexpectedTenantException(msg)
            return node
    
    node.add_label(tenant_label)
    return node

def _try_add_graph_label_to_node(node: CypherNode, graph:str) -> CypherNode:
    graph_label = f"GRAPH_{graph}"
    for label in node.labels:
        if label.startswith("GRAPH"):
            if label != graph_label:
                msg = f"Node {node.variable} already has a graph label {label}"
                raise CypherNodeUnexpectedGraphException(msg)
            return node
    node.add_label(graph_label)
    return node

def validate_node_graph_and_tenant(
        node: CypherNode,
        graph: str,
        tenant: str,
) -> None:
    _try_add_graph_label_to_node(node, graph)
    _try_add_tenant_lable_to_node(node, tenant)


async def execute_cypher_query(
        driver: neo4j.AsyncDriver,
        query: str,
        parameters: dict | None = None,
) -> neo4j.AsyncResult:
    async def inner() -> neo4j.AsyncResult:
        async with driver.session() as session:
            return await session.run(query, parameters)

    return await asyncio.shield(inner())

async def execute_cypher_batch_query(
        driver: neo4j.AsyncDriver,
        queries: List[Tuple[str, dict | None]],
):
    async def inner() -> neo4j.AsyncResult:
        async with driver.session() as session:  # noqa: SIM117
            async with await session.begin_transaction() as tx:
                for query, parameters in queries:
                    tx.run(query, parameters)

    return await asyncio.shield(inner())

def create_node_cypher_query(
        graph: str,
        tenant: str,
        node: CypherNode | CypherNodeList,
    ) -> str:
    if isinstance(node, CypherNode):
        validate_node_graph_and_tenant(node, graph, tenant)
    elif isinstance(node, CypherNodeList):
        for n in node:
            validate_node_graph_and_tenant(n, graph, tenant)
    else:
        raise ValueError("Invalid node type")
    
    return f"CREATE {str(node)}"
    
def create_edge_between_two_exist_node_cypher_query(
        graph: str,
        tenant: str,
        node1: CypherNode,
        node2: CypherNode,
        edge: CypherEdge,
) -> str:
    validate_node_graph_and_tenant(node1, graph, tenant)
    validate_node_graph_and_tenant(node2, graph, tenant)
    if node1.variable is None:
        node1.set_variable("m")
    if node2.variable is None:
        node2.set_variable("n")
    if node1.variable == node2.variable:
        raise ValueError("Node1 and Node2 cannot has the same variable")
    
    v1 = node1.variable
    v2 = node2.variable

    return f"""
        MATCH {str(node1)}, {str(node2)}
        WITH {v1}, {v2}, count({v1}) as {v1}_count, count({v2}) as {v2}_count
        WHERE {v1}_count = 1 AND {v2}_count = 1 AND {v1} <> {v2}
        CREATE ({v1}){str(edge)}({v2})
        RETURN r
    """

def batch_create_nodes_and_edges_cypher_query(
        graph: str,
        tenant: str,
        nodes: Iterable[CypherNode],
        edges_pattern: list[CypherPattern],
) -> str:
    # check all nodes has different variable and not None
    node_variables = [n.variable for n in nodes]
    if not all(n.variable is not None for n in nodes):
        raise ValueError("Some nodes has not variable")
    if len(node_variables) != len(set(node_variables)):
        raise ValueError("Nodes has same variable")
    # check all edges pattern`s nodes has reference variable to exist nodes
    for p in edges_pattern:
        for n in p.get_nodes():
            if n.variable not in node_variables:
                raise ValueError("Some edges pattern`s nodes has not reference variable to exist nodes")

    for node in nodes:
        validate_node_graph_and_tenant(node, graph, tenant)

    node_str = [str(n) for n in nodes]
    pattern_str = [str(p) for p in edges_pattern]

    return f"""
        CREATE {",\n".join(node_str + pattern_str)}
    """

def retrive_pattern_cypher_query(
        graph: str,
        tenant: str,
        pattern: CypherPattern,
) -> str:
    for n in pattern.get_nodes():
        validate_node_graph_and_tenant(n, graph, tenant)
    ret_var = [ele.variable for ele in pattern.elements]
    # remove None in ret_var
    ret_var = [v for v in ret_var if v is not None]

    return f"MATCH {str(pattern)} RETURN {','.join(ret_var)}"

def update_node_cypher_query(
        graph: str,
        tenant: str,
        node: CypherNode,
        properties: dict,
) -> str:
    # check node has variable
    if node.variable is None:
        n_var = "n"
        node.set_variable(n_var)
    else:
        n_var = node.variable

    validate_node_graph_and_tenant(node, graph, tenant)
    n_4_format = CypherNode(properties=properties)
    return f"MATCH {str(node)} SET {n_var} += {n_4_format._format_properties()}"


def update_edge_cypher_query(
        graph: str,
        tenant: str,
        edge_pattern: CypherPattern,
        properties: dict,
) -> str:
    # validate edge_pattern
    for node in edge_pattern.get_nodes():
        validate_node_graph_and_tenant(node, graph, tenant)

    # check edge_pattern has edge and only one edge has variable
    edges = edge_pattern.get_edges()
    edges_var = [ele.variable for ele in edges]
    if len(edges_var) == 1:
        if edges_var[0] is None:
            e_var = "e"
        else:
            e_var = edges_var[0]
    
    else:
        edges_var = [v for v in edges_var if v is not None]
        if len(edges_var) != 1:
            raise ValueError("Edge pattern with multiple edges must have only one edge with variable")
        e_var = edges_var[0]

    e_4_format = CypherEdge(properties=properties)
    return f"MATCH {edge_pattern} SET {e_var} += {e_4_format._format_properties()}"

def safe_delete_node_cypher_query(
        graph: str,
        tenant: str,
        node: CypherNode,
) -> str:
    validate_node_graph_and_tenant(node, graph, tenant)

    # check node has variable
    if node.variable is None:
        n_var = "n"
        node.set_variable(n_var)
    else:
        n_var = node.variable

    return f"MATCH {str(node)} NODETACH DELETE {n_var}"

def force_delete_node_cypher_query(
        graph: str,
        tenant: str,
        node: CypherNode,
) -> str:
    validate_node_graph_and_tenant(node, graph, tenant)

    # check node has variable
    if node.variable is None:
        n_var = "n"
        node.set_variable(n_var)
    else:
        n_var = node.variable

    return f"MATCH {str(node)} DETACH DELETE {n_var}"

def safe_delete_node_in_pattern_cypher_query(
        graph: str,
        tenant: str,
        pattern: CypherPattern,
        delete_node_variable: list[str] | None = None,
) -> str:
    nodes = pattern.get_nodes()
    for node in nodes:
        validate_node_graph_and_tenant(node, graph, tenant)

    if not delete_node_variable:
        delete_node_variable = [ele.variable for ele in nodes if ele.variable is not None]
    if not delete_node_variable:
        raise ValueError("No valid node variable found")
    
    return f"MATCH {pattern} NODETACH DELETE {','.join(delete_node_variable)}"

def force_delete_node_in_pattern_cypher_query(
        graph: str,
        tenant: str,
        pattern: CypherPattern,
        delete_node_variable: list[str] | None = None,
) -> str:
    nodes = pattern.get_nodes()
    for node in nodes:
        validate_node_graph_and_tenant(node, graph, tenant)

    if not delete_node_variable:
        delete_node_variable = [ele.variable for ele in nodes if ele.variable is not None]
    if not delete_node_variable:
        raise ValueError("No valid node variable found")
    
    return f"MATCH {pattern} DETACH DELETE {','.join(delete_node_variable)}"

def delete_edge_in_pattern_cypher_query(
        graph: str,
        tenant: str,
        pattern: CypherPattern,
        delete_edge_variable: list[str] | None = None,
) -> str:
    for node in pattern.get_nodes():
        validate_node_graph_and_tenant(node, graph, tenant)
    
    if not delete_edge_variable:
        delete_edge_variable = [ele.variable for ele in pattern.get_edges() if ele.variable is not None]
    if not delete_edge_variable:
        raise ValueError("No valid edge variable found")
    
    return f"MATCH {pattern} DELETE {','.join(delete_edge_variable)}"
    
