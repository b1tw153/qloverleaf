import time
from dataclasses import dataclass, field

from lark import Token, Tree


@dataclass
class Stats:
    start_time: float = field(default_factory=time.time)
    parse_time: float = 0.0
    interpreter_time: float = 0.0
    translator_time: float = 0.0
    qlever_time: float = 0.0
    post_processor_time: float = 0.0
    output_formatter_time: float = 0.0
    end_time: float = 0.0

@dataclass
class Query:
    text: str
    tree: Tree[Token]
    stats: Stats = field(default_factory=Stats)
