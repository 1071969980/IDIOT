from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from api.graph_executor.graph import Graph

from dataclasses import dataclass
import math
from typing import Optional, Union
from api.graph_executor.graph_core import ParamsLineageDict, ParamsList, BypassSignal


@Graph("test") # register node A to the graph named "test"
@dataclass # a valid node must be a dataclass
class A: # declare A as a graph node in the graph named "test"
    f_msg: str
    f_num: int | None = 0
    
    # def what while happen when node A is executed in run method
    def run(self) -> tuple["B", "C"]: # used return annotation to declare the successor nodes of node A. 
                                      # tuple and forward def is available. 
                                      # tuple means the node A will have two successor nodes B and C.
        # do something
        self.f_num += 100
        self.f_msg += " | A processed"
        # return a tuple of successor nodes instances. 
        # These instance will be passed to the successor nodes init method after casting into dict.
        return B(self.f_num, self.f_msg), C(self.f_num, self.f_msg)
        # or you can return a dict to pass only patitial parameters to the successor nodes.
        return {
            B: {"f_num": self.f_num}, # B will receive only f_num from A
            C: {"f_msg": self.f_msg}, # C will receive only f_msg from A
        }
        
@Graph("test")
@dataclass
class B:
    f_num: int | None
    f_msg: str | None
    
    # "a_node: A" declare a parameter will fetch the executed node A instance
    def run(self, a_node: A) -> tuple["C", "D"]:
        if self.f_num >= 200:
            # BypassSignal will skip the node D
            # but node C will still be executed, because node C also is a successor of node A
            return BypassSignal(C), BypassSignal(D)
        self.f_msg = f"{a_node.f_msg} | B processed"
        return C(self.f_num + 1, self.f_msg + "| passing to C")

@Graph("test")
@dataclass
class C:
    # just declare as ParamsList (totally same as list), because A and B send data to C at same time.
    f_num: ParamsList[int] | None 
    # just declare as ParamsLineageDict (totally same as dict), because A and B send data to C at same time.
    # different ParamsList, dict will be {"source_name": "data", ...}
    f_msg: ParamsLineageDict[str] | None 
    
    def run(self, a_node: A) -> None: 
        num = sum(self.f_num)
        self.msg = " /:/ ".join(self.f_msg.values())
        assert num >= a_node.f_num

@Graph("test")
@dataclass
class D:
    f_num: int | None
    f_msg: str | None
    
    def run(self) -> None:
        pass

if __name__ == "__main__":
    # a = A("1", 20)
    a = A("1", 120) # passing number greater than 100 to node A will make node B send bypass signal to node C、D
    nodes, passing_params = Graph.start("test", a, 1)
    pass