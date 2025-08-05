import inspect
import types
from typing import Callable, Any, Union, get_args

from .exceptions import MissingRunMethodError
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
    
    def start(self, name: str, seed: Any | None = None, workers_num: int = 1):
        return self._graphs[name].start(seed, workers_num)
    
    def render_as_mermaid(self,
                          name: str,
                          save_to: str | None = None,
                          ink_service_base_url: str | None = None):
        return self._graphs[name].render_as_mermaid(save_to, ink_service_base_url)


Graph = GraphMgr()

