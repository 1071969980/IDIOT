from collections.abc import Callable
from typing import Generator, Any, Literal, overload

from .graph_core import _Graph


class GraphMgr:
    def __init__(self) -> None:
        self._graphs: dict[str, _Graph] = {}
        
    def __call__(self, name: str) -> Callable:
        def decorator(cls: type) -> type:
            if name not in self._graphs:
                self._graphs[name] = _Graph(name)
                graph = self._graphs[name]
            else:
                graph = self._graphs[name]

            graph.set_node_def(cls)
            return cls

        return decorator


    @overload
    async def start(self,
                    name: str,
                    seed: Any | None = None,
                    /,
                    *,
                    yield_return: Literal[True],
                    injected_finalized_nodes,
                    injected_init_param_pool) -> Generator[tuple[str, dict[str, Any], dict[str, Any]]] :
        ...

    
    @overload
    async def start(self,
                    name: str,
                    seed: Any | None = None,
                    /,
                    *,
                    yield_return: Literal[False] = False,
                    injected_finalized_nodes,
                    injected_init_param_pool) -> tuple[dict[str, Any], dict[str, Any]] :
        ...

    async def start(self, 
                    name: str, 
                    seed: Any | None = None, 
                    /,
                    *,
                    yield_return: bool = False,
                    injected_finalized_nodes = None,
                    injected_init_param_pool = None) -> tuple[dict[str, Any], dict[str, Any]] :
        return await self._graphs[name].start(seed,
                                              yield_return=yield_return,
                                              injected_finalized_nodes = injected_finalized_nodes,
                                              injected_init_param_pool = injected_init_param_pool)
    

    
    def render_as_mermaid(self,
                          name: str,
                          save_to: str | None = None,
                          ink_service_base_url: str | None = None):
        return self._graphs[name].render_as_mermaid(save_to, ink_service_base_url)


Graph = GraphMgr()

