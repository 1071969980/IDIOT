class MissingRunMethodError(Exception): pass
class UnExpectedNodeError(Exception): 
    def __init__(self, message, init_prama_pool, finalized_nodes_dict, *agrs) -> None:
        super().__init__(message, *agrs)
        self.init_prama_pool = init_prama_pool
        self.finalized_nodes_dict = finalized_nodes_dict