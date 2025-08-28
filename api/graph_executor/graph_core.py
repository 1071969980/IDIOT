import graphlib
import inspect
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import Field, is_dataclass
from threading import Lock
from types import NoneType, UnionType
from typing import Any, ForwardRef, Optional, Union, get_args, get_origin, overload, Literal, Iterable

from asyncio.taskgroups import TaskGroup
from asyncio.queues import Queue
from .exceptions import MissingRunMethodError, UnExpectedNodeError

import logfire
from pathlib import Path
from PIL import Image as im
import io
import requests
import base64

class ParamsLineageDict(dict):pass
class ParamsList(list):pass

class BypassSignal:
    def __init__(self, target_node: str | type) -> None:
        if isinstance(target_node, str):
            self.target_node = target_node
        elif isinstance(target_node, type):
            self.target_node = target_node.__name__
        else:
            raise TypeError("node must be a string or a type")

class _Graph:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.node_def: dict[str, type] = {}
        self.node_successor: dict[str, set[str]] = {}
        self.node_pull_sources: dict[str, dict[str, str]] = {} # {node_name: {param_name: node_name}}
        
    def _validate_node_def(self, node: type) -> None:
        # check node is a dataclass
        if not is_dataclass(node):
            msg = f"{node.__name__} is not a dataclass."
            raise TypeError(msg)
        
        class_name = node.__name__
        members = inspect.getmembers(node)
        # check there is run method in the class
        if not any(member[0] == "run" and inspect.isfunction(member[1]) for member in members):
            msg = f"Class {class_name} does not have a method named 'run'."
            raise MissingRunMethodError(msg)
        _run_method = next(member[1] for member in members if member[0] == "run" and inspect.isfunction(member[1]))
        _run_annotation = _run_method.__annotations__
        # check run method is async function
        if not inspect.iscoroutinefunction(_run_method):
            msg = f"Method 'run' in class {class_name} is not a coroutine function."
            raise TypeError(msg)
        # check all the parameters has annotations
        _run_signature = inspect.signature(_run_method)
        for param_name, param in _run_signature.parameters.items():
            if param_name in ("self", "cls", "return"):
                continue
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            if param.annotation == inspect.Parameter.empty:
                hint = "All parameters must have annotations."
                msg = f"The parameter '{param_name}' in method 'run' in class {class_name} does not have an annotation."
                raise TypeError(hint, msg)

    def _register_node_successor(self, cls_name, run_method) -> None:
        # get the parameters and annotations of the run method
        _run_annotation = run_method.__annotations__
        
        # register the node successor
        return_annotation = _run_annotation.get("return", None)
        if return_annotation:
            # check if the return annotation is a Tuple
            origin = get_origin(return_annotation)
            if origin is not None and origin is tuple:
                successors = set()
                for arg in get_args(return_annotation):
                    if isinstance(arg, (ForwardRef)):
                        successors.add(arg.__forward_arg__)
                    elif isinstance(arg, str):
                        successors.add(arg)
                    else:
                        successors.add(arg.__name__)
            # check if the return annotation is a ForwardRef or str
            elif isinstance(return_annotation, (ForwardRef, str)):
                successors = set()
                if isinstance(return_annotation, str):
                    successors.add(return_annotation)
                else:
                    successors.add(return_annotation.__forward_arg__)
            else:
                successors = set()
                successors.add(return_annotation.__name__)
            self.node_successor[cls_name] = successors
        else:
            self.node_successor[cls_name] = set()
            
    def _register_node_pull_sources(self, cls_name: str, run_method: Callable) -> None:
        _run_annotation = run_method.__annotations__
        _run_signature = inspect.signature(run_method)
        node_pull_sources = {}
        for param_name, param in _run_signature.parameters.items():
            if param_name in ("self", "cls"):
                continue
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            param_annotation = _run_annotation.get(param_name, None)
            if param_annotation:
                if isinstance(param_annotation, (ForwardRef, str)):
                    node_pull_sources[param_name] = param_annotation
                else:
                    node_pull_sources[param_name] = param_annotation.__name__
            else:
                msg = f"The parameter '{param_name}' in method 'run' in class {cls_name} does not have an annotation."
                raise TypeError(msg)
        self.node_pull_sources[cls_name] = node_pull_sources

    def set_node_def(self, node: type) -> None:
        if node.__name__ in self.node_def:
            msg = f"Node {node.__name__} is already registered"
            raise ValueError(msg)
        
        self._validate_node_def(node)
        
        class_name = node.__name__
        members = inspect.getmembers(node)
        _run_method = next(member[1] for member in members if member[0] == "run" and inspect.isfunction(member[1]))

        self.node_def[class_name] = node
        
        self._register_node_successor(class_name, _run_method)
            
        # register the node pull sources
        self._register_node_pull_sources(class_name, _run_method)
    
    def _validate_graph_node_def(self) -> dict[str, set[str]]:
        """
        Check if the graph is valid
        """
        # validate all key in self.node_successors are in self.node_def
        for key in self.node_successor:
            if key not in self.node_def:
                msg = f"Node {key} is not registered"
                raise ValueError(msg)
        # validate each node has a valid successor which is in self.node_def
        for node_name, node_successor in self.node_successor.items():
            for successor in node_successor:
                if successor not in self.node_def:
                    msg = f"{node_name} successor {successor} is not registered"
                    raise ValueError(msg)
                
        # validate all key in self.node_pull_sources is in self.node_def
        for key in self.node_pull_sources:
            if key not in self.node_def:
                msg = f"{key} is not registered"
                raise ValueError(msg)
        # validate each node has a valid pull sources which is in self.node_def
        for deps in self.node_pull_sources.values():
            for dep in deps.values():
                if dep not in self.node_def:
                    msg = f"{dep} is not registered"
                    raise ValueError(msg)
                
        # merge dependency and successor graph
        successor_graph_from_dep:  dict[str, set[str]] = {}
        for node, deps in self.node_pull_sources.items():
            for dep in deps.values():
                if dep not in successor_graph_from_dep:
                    successor_graph_from_dep[dep] = set()
                successor_graph_from_dep[dep].add(node)
                
        merged_successor_graph = deepcopy(self.node_successor)
        for node, successor in successor_graph_from_dep.items():
            if node not in merged_successor_graph:
                merged_successor_graph[node] = set()
            merged_successor_graph[node].update(successor)
            
        # invert successor graph to be predecessor graph
        predecessor_graph_from_successor: dict[str, set[str]] = {}
        for node, successors in merged_successor_graph.items():
            for successor in successors:
                if successor not in predecessor_graph_from_successor:
                    predecessor_graph_from_successor[successor] = set()
                predecessor_graph_from_successor[successor].update(node)
            
        return predecessor_graph_from_successor
                
    def _update_to_param_pool(self,
                              param_poll: dict[str | type, dict[str, Any]],
                              source_name: str,
                              data: Any) -> None:
        def __update_to_param_pool(param_poll: dict[str, dict[str, Any]],
                                   source_name: str,
                                   name: str | type,
                                   data: dict[str, Any]) -> None:
            if isinstance(name, type):
                name = name.__name__
            if name not in self.node_def:
                msg = f"{name} is not registered"
                raise ValueError(msg)
            if name not in param_poll:
                warp_data = { k : ParamsLineageDict() for k in data.keys() }
                for k, v in data.items():
                    warp_data[k][source_name] = v
                param_poll[name] = warp_data
            else:
                exist_data = param_poll[name]
                for k, v in data.items():
                    if k not in exist_data:
                        exist_data[k] = ParamsLineageDict()
                        exist_data[k][source_name] = v
                    else:
                        exist_data[k][source_name] = v
        
        if isinstance(data, tuple):
            for n in data:
                self._update_to_param_pool(param_poll, source_name, n)
        elif isinstance(data, BypassSignal):
            __update_to_param_pool(param_poll, source_name, data.target_node, {"__bypass__": data})
        elif is_dataclass(data):
            if data.__class__.__name__ not in self.node_def:
                msg = f"{data.__class__.__name__} is not registered"
                raise ValueError(msg)
            name = data.__class__.__name__
            params = data.__dict__
            __update_to_param_pool(param_poll, source_name, name, params)
        elif isinstance(data, dict):
            for name, params in data.items():
                assert isinstance(params, dict), f"{params} is not a dict"
                __update_to_param_pool(param_poll, source_name, name, params)
        else:
            msg = f"{data} is not a dataclass or dict, or BypassSignal"
            raise TypeError(msg)
        
    async def start(self,
              seed: Any | None = None,
              /,
              *,
              yield_return: bool = False,
              injected_finalized_nodes = None,
              injected_init_param_pool = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """_summary_
        will execute the graph by theardpoll.
        
        Returns:
            tuple[dict[str, Any], dict[str, Any]]: finalized_nodes_dict, init_param_pool
        """
        
        _graph = self._validate_graph_node_def()
        try:
            topo_graph = graphlib.TopologicalSorter(_graph)
            topo_graph.prepare()
        except graphlib.CycleError as e:
            msg = f"The graph is not a DAG, there is a cycle in the graph: {e}"
            raise ValueError(msg)
        
        # {nodename: {param_name: {source_name: param_value}}}
        _init_param_pool : dict[str, dict[str, dict[str, Any]]] = injected_init_param_pool if injected_init_param_pool else {}
        _init_param_pool_lock = Lock()
        
        _finalized_nodes_dict = injected_finalized_nodes if injected_finalized_nodes else {}
        _finalized_nodes_dict_lock = Lock()
        _finalized_nodes_queue = Queue()
        
        
        def _processe_node_params(node: str, 
                                 node_feilds: dict[str, Field[Any]],
                                 node_params: dict[str, dict[str, dict[str, Any]]]):
            processed_node_params = {}
            for p_name, p_values in node_params.items():
                if p_name == "__bypass__":
                    continue
                if p_name not in node_feilds:
                    raise ValueError(f"node param {p_name} not found in node {node} definition")
                field_type = node_feilds[p_name].type
                if ((get_origin(field_type) is Optional) or\
                            (get_origin(field_type) is Union) or \
                            (get_origin(field_type) is UnionType)):
                    if NoneType not in get_args(field_type):
                        raise ValueError(f"node param {p_name} is not optional in node {node} definition")
                    if ParamsLineageDict in get_args(field_type):
                        field_type = ParamsLineageDict
                    elif ParamsList in get_args(field_type):
                        field_type = ParamsList
                    else:
                        for _t in get_args(field_type):
                            if _t is not NoneType:
                                field_type = _t
                                break
                if get_origin(field_type) is ParamsLineageDict:
                    processed_node_params[p_name] = p_values
                elif get_origin(field_type) is ParamsList:
                    processed_node_params[p_name] = ParamsList(p_values.values())
                else:
                    if len(p_values) > 1:
                        raise ValueError(f"{node} field {p_name} anotated as {node_feilds[p_name].type} can only have one value source")
                    processed_node_params[p_name] = next(iter(p_values.values()))
            return processed_node_params
        
        def _should_be_bypassed(node: str, 
                                node_params: dict[str, dict[str, Any]]) -> bool:
            bypass_signal = node_params.get("__bypass__", None)
            if not bypass_signal:
                return False
            # get all predecessors
            predecessors = [
                pred
                for pred, ss in self.node_successor.items() if node in ss
            ]
            bypass_source = list(bypass_signal.keys())
            return all(pred in bypass_source for pred in predecessors)
                
        async def _node_execute_task(node: str) -> None:
            try:
                node_def = self.node_def[node]
                assert is_dataclass(node_def), f"node_def {node_def} is not a dataclass"
                node_feilds = node_def.__dataclass_fields__
                
                # create node instance
                with _init_param_pool_lock:
                    node_params = _init_param_pool.get(node, {})
                    # check is the node should be bypassed
                    should_bypass = _should_be_bypassed(node, node_params)
                    # process node params by node_def fields type annotation
                    if not should_bypass:
                        processed_node_params = _processe_node_params(node, node_feilds, node_params)
                
                if should_bypass:
                    # throw bypass signal to all downstream nodes
                    node_instance = None
                    with _init_param_pool_lock:
                        self._update_to_param_pool(
                            _init_param_pool,
                            node,
                            tuple([
                                BypassSignal(ss)
                                for ss in self.node_successor[node]
                            ]),
                        )
                    with _finalized_nodes_dict_lock:
                        _finalized_nodes_dict[node] = node_instance
                        
                else:
                    # call run method
                    node_instance = node_def(**processed_node_params)
                    
                    # coleecte run pull sources
                    with _finalized_nodes_dict_lock:
                        run_params = { k: _finalized_nodes_dict.get(v) for k, v in self.node_pull_sources[node].items() }
                    
                    # invoke run method
                    run_result = await node_instance.run(**run_params)
                    
                    with _init_param_pool_lock:
                        if run_result is not None:
                            self._update_to_param_pool(_init_param_pool, node, run_result)
                        
                    # update node instance to finalized nodes dict
                    with _finalized_nodes_dict_lock:
                        _finalized_nodes_dict[node] = node_instance
                
            except Exception:
                raise
            finally:
                await _finalized_nodes_queue.put(node)
                                       
        tg = TaskGroup()
        with logfire.span(f"Graph {self.name}"):
            if seed:
                self._update_to_param_pool(_init_param_pool, "__start__", seed)
            
            try:
                async with tg:
                    active_nodes = set()

                    while topo_graph.is_active():
                        for node in topo_graph.get_ready():
                            with logfire.span(f"Graph {self.name}::{node}"):
                                if node in _finalized_nodes_dict:
                                    topo_graph.done(node)
                                    logfire.info(f"Node {node} is already finalized")
                                else:
                                    tg.create_task(_node_execute_task(node))
                                    active_nodes.add(node)
                        
                        if active_nodes:
                            node = await _finalized_nodes_queue.get()
                            topo_graph.done(node)
                            active_nodes.remove(node)
                        if yield_return:
                            yield node, _finalized_nodes_dict, _init_param_pool
            # catch exception from task group
            except Exception as e:
                raise UnExpectedNodeError(f"during run {node}",
                                        _init_param_pool,
                                        _finalized_nodes_dict) from e
                
        return _finalized_nodes_dict, _init_param_pool
        
    def render_as_mermaid(self,
                          save_to: Path | None = None,
                          ink_service_base_url: str | None = None) -> str:
        """
        render graph as mermaid
        """
        # merge dependency and successor graph
        successor_graph_from_dep:  dict[str, set[str]] = {}
        for node, deps in self.node_pull_sources.items():
            for dep in deps.values():
                if dep not in successor_graph_from_dep:
                    successor_graph_from_dep[dep] = set()
                successor_graph_from_dep[dep].add(node)
                
        # merged_successor_graph = deepcopy(self.node_successor)
        # for node, successor in successor_graph_from_dep.items():
        #     if node not in merged_successor_graph:
        #         merged_successor_graph[node] = set()
        #     merged_successor_graph[node].update(successor)
        
        mm_str = "graph LR;\n"
        for node, successor in self.node_successor.items():
            if not successor:
                continue
            mm_str += "\t"
            mm_str += f"{node} ==> "
            mm_str += " & ".join([f"{s}" for s in successor])
            mm_str += "\n"
        
        for node, successor in successor_graph_from_dep.items():
            if not successor:
                continue
            mm_str += "\t"
            mm_str += f"{node} -. pull .-> "
            mm_str += " & ".join([f"{s}" for s in successor])
            mm_str += "\n"
        
            
        if save_to:
            if not ink_service_base_url:
                ink_service_base_url = 'https://mermaid.ink/img/'
            graphbytes = mm_str.encode("utf8")
            base64_bytes = base64.urlsafe_b64encode(graphbytes)
            base64_string = base64_bytes.decode("ascii")
            img = im.open(io.BytesIO(requests.get(ink_service_base_url + base64_string).content))
            img.save(save_to)
            
        return mm_str
            
        
            
