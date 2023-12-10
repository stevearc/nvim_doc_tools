import os
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, List

from pyparsing import (
    Forward,
    Keyword,
    LineEnd,
    LineStart,
    Literal,
    OneOrMore,
    Opt,
    ParserElement,
    QuotedString,
    Regex,
    Suppress,
    White,
    Word,
    ZeroOrMore,
    alphanums,
    alphas,
    delimitedList,
)
from pyparsing.exceptions import ParseException

FN_RE = re.compile(r"^M\.(\w+)\s*=|^function ([A-Z][A-Za-z0-9_:\.]*)\s*\(")

__all__ = ["LuaFunc", "LuaParam", "LuaReturn", "parse_functions", "render_api"]


@dataclass
class LuaFunc:
    name: str
    summary: str = ""
    params: List["LuaParam"] = field(default_factory=list)
    returns: List["LuaReturn"] = field(default_factory=list)
    example: str = ""
    note: str = ""
    private: bool = False
    deprecated: bool = False
    raw_annotation: List[str] = field(default_factory=list)

    @classmethod
    def parse_annotation(cls, name: str, lines: List[str]) -> "LuaFunc":
        # Strip off the leading comment
        lines = [line[3:] for line in lines]
        try:
            p = annotation.parseString("".join(lines), parseAll=True)
        except ParseException as e:
            raise Exception(f"Error parsing {name}") from e
        params = []
        returns = []
        for item in p.asList():
            if isinstance(item, LuaParam):
                params.append(item)
            elif isinstance(item, LuaReturn):
                returns.append(item)
        return cls(
            name,
            summary=p.get("summary", ""),
            private="private" in p,
            deprecated="deprecated" in p,
            example=p.get("example", ""),
            note=p.get("note", ""),
            params=params,
            returns=returns,
        )


@dataclass
class LuaParam:
    name: str
    type: str
    desc: str = ""
    subparams: List["LuaParam"] = field(default_factory=list)

    @classmethod
    def from_parser(cls, p):
        sp = p["subparams"].asList() if "subparams" in p else []
        ptype = p["type"]
        if "optional" in p:
            ptype = "nil|" + ptype
        return cls(
            p["name"],
            ptype,
            desc=p.get("desc", ""),
            subparams=sp,
        )


@dataclass
class LuaReturn:
    type: str
    desc: str = ""

    @classmethod
    def from_parser(cls, p):
        name, *desc = p.asList()
        return cls(name, "".join(desc))


ParserElement.setDefaultWhitespaceChars(" \t")

varname = Word(alphas, alphanums + "_")
lua_type = Forward()
primitive_type = (
    Keyword("nil")
    | Keyword("string")
    | Keyword("integer")
    | Keyword("boolean")
    | Keyword("number")
    | Keyword("table")
    | QuotedString('"', unquote_results=False)
    | Keyword("any")
    | Regex(r"\w+\.[\w]+(\[\])?")
)
lua_list = (
    Keyword("string[]")
    | Keyword("integer[]")
    | Keyword("number[]")
    | Keyword("any[]")
    | Keyword("boolean[]")
    | Keyword("table[]")
)
lua_table = (
    Keyword("table") + "<" + lua_type + "," + Opt(White()) + lua_type + ">"
).setParseAction(lambda p: "".join(p.asList()))
lua_func_param = (
    Opt(White()) + ("..." | varname) + ":" + Opt(White()) + lua_type + Opt(White())
).setParseAction(lambda p: "".join(p.asList()))
lua_func = (
    Keyword("fun")
    + "("
    + Opt(delimitedList(lua_func_param, combine=True))
    + ")"
    + Opt((":") + Opt(White()) + lua_type)
).setParseAction(lambda p: "".join(p.asList()))
non_union_types = lua_list | lua_table | lua_func | primitive_type
union_type = delimitedList(non_union_types, delim="|").setParseAction(
    lambda p: "|".join(p.asList())
)
lua_type <<= union_type | non_union_types

tag = Forward()
subparam = (
    Suppress(LineStart())
    + Suppress(White())
    + varname.setResultsName("name")
    + Opt(Literal("?")).setResultsName("optional")
    + lua_type.setResultsName("type")
    + Opt(Regex(".+").setResultsName("desc"))
    + Suppress(LineEnd())
).setParseAction(LuaParam.from_parser)
tag_param = (
    Suppress("@param")
    + varname.setResultsName("name")
    + Opt(Literal("?")).setResultsName("optional")
    + lua_type.setResultsName("type")
    + Opt(Regex(".+").setResultsName("desc"))
    + Suppress(LineEnd())
    + ZeroOrMore(subparam).setResultsName("subparams")
).setParseAction(LuaParam.from_parser)
tag_private = (Keyword("@private") + Suppress(LineEnd())).setResultsName("private")
tag_deprecated = (Keyword("@deprecated") + Suppress(LineEnd())).setResultsName(
    "deprecated"
)

tag_example = (
    (
        Suppress("@example" + LineEnd())
        + OneOrMore(
            LineStart()
            + Suppress(White(max=1))
            + Opt(White())
            + Regex(r".+")
            + LineEnd()
        )
    )
    .setResultsName("example")
    .setParseAction(lambda p: "".join(p.asList()))
)
tag_note = (
    (
        Suppress("@note" + LineEnd())
        + OneOrMore(
            LineStart()
            + Suppress(White(max=1))
            + Opt(White())
            + Regex(r".+")
            + LineEnd()
        )
    )
    .setResultsName("note")
    .setParseAction(lambda p: "".join(p.asList()))
)
tag_return = (
    Suppress("@return") + lua_type + Regex(".*").setName("desc") + Suppress(LineEnd())
).setParseAction(LuaReturn.from_parser)
summary = Regex(r"^[^@].+").setResultsName("summary") + Suppress(LineEnd())

tag <<= tag_param | tag_private | tag_return | tag_example | tag_note | tag_deprecated

annotation = Opt(summary) + ZeroOrMore(tag) + Suppress(ZeroOrMore(White()))


def _parse_lines(lines: Iterable[str]) -> List[LuaFunc]:
    funcs = []
    chunk = []
    for line in lines:
        if line.startswith("---"):
            chunk.append(line)
        elif chunk:
            m = FN_RE.match(line)
            if m:
                # temporary hack: ignore @type module variables
                if any([c.startswith("---@type") for c in chunk]):
                    chunk = []
                    continue
                func = LuaFunc.parse_annotation(m[1] or m[2], chunk)
                if func is not None:
                    func.raw_annotation = chunk
                    funcs.append(func)
            chunk = []
    return funcs


def parse_functions(filename: str) -> List[LuaFunc]:
    with open(filename, "r", encoding="utf-8") as ifile:
        return _parse_lines(ifile)


def render_api(funcs: List[LuaFunc], format: Callable[[LuaFunc], str]) -> List[str]:
    ret = []
    for func in funcs:
        if func.private:
            continue
        ret.extend(func.raw_annotation)
        ret.append(format(func) + "\n")
    return ret
