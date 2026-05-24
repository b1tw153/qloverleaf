import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from lark import Token, Tree

from qloverleaf.transformer import Query


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
class Bbox:
    south: str
    west: str
    north: str
    east: str


class OutputFormat(Enum):
    XML = "xml"
    JSON = "json"
    CSV = "csv"
    CUSTOM = "custom"
    POPUP = "popup"


@dataclass
class QueryContext:
    text: str
    tree: Tree[Token]
    stats: Stats = field(default_factory=Stats)
    timeout: int = 180
    maxsize: int = 2048 * 1024
    bbox: Optional[Bbox] = None
    out: OutputFormat = OutputFormat.XML
    out_params: Optional[Tree[Token]] = None
    ir: Optional[Query] = None
