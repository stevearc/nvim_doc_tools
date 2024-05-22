import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Type

from pyparsing import (
    Forward,
    Keyword,
    LineEnd,
    LineStart,
    Literal,
    OneOrMore,
    Opt,
    ParserElement,
    ParseResults,
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


@dataclass
class LuaTypes:
    files: Dict[str, "LuaFile"] = field(default_factory=dict)
    classes: Dict[str, "LuaClass"] = field(default_factory=dict)

    def add_file(self, filename: str, file: "LuaFile"):
        self.files[filename] = file
        for c in file.classes:
            self.classes[c.name] = c


@dataclass
class LuaFile:
    functions: List["LuaFunc"] = field(default_factory=list)
    classes: List["LuaClass"] = field(default_factory=list)


@dataclass
class LuaClass:
    name: str
    parent: Optional[str] = None
    fields: List["LuaField"] = field(default_factory=list)

    @classmethod
    def parse_lines(cls, lines: List[str]) -> Optional["LuaClass"]:
        # Strip off the leading comment
        lines = [line[3:] for line in lines]
        try:
            p = lua_class.parseString("".join(lines), parseAll=True)
        except ParseException as e:
            return None
        return cls.from_parser(p)

    @classmethod
    def from_parser(cls: Type["LuaClass"], parse_result: ParseResults) -> "LuaClass":
        return cls(
            parse_result.get("name"),
            parent=parse_result.get("parent"),
            fields=parse_result.get("fields").as_list(),
        )

    def convert_to_subparams(self) -> List["LuaParam"]:
        params = []
        for fld in self.fields:
            if fld.name and (fld.scope is None or fld.scope == Scope.PUBLIC):
                params.append(
                    LuaParam(
                        fld.name,
                        fld.type,
                        desc=fld.desc,
                    )
                )
        return params


@dataclass
class LuaField:
    type: str
    # Name is None if key_type is not None
    name: Optional[str] = None
    key_type: Optional[str] = None
    desc: str = ""
    scope: Optional["Scope"] = None

    @classmethod
    def from_parser(cls: Type["LuaField"], parse_result: ParseResults) -> "LuaField":
        return cls(
            name=parse_result.get("name"),
            type=parse_result.get("type"),
            key_type=parse_result.get("key_type"),
            desc=parse_result.get("desc", ""),
            scope=parse_result.get("scope"),
        )


class Scope(Enum):
    PRIVATE = 1
    PROTECTED = 2
    PACKAGE = 3
    PUBLIC = 4


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
    def parse_annotation(cls, name: str, lines: List[str]) -> Optional["LuaFunc"]:
        # Strip off the leading comment
        lines = [line[3:] for line in lines]
        try:
            p = annotation.parseString("".join(lines), parseAll=True)
        except ParseException as e:
            return None
        params = []
        returns = []
        for item in p.as_list():
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
        sp = p["subparams"].as_list() if "subparams" in p else []
        ptype = p["type"]
        if "optional" in p:
            ptype = "nil|" + ptype
        return cls(
            p["name"],
            ptype,
            desc=p.get("desc", ""),
            subparams=sp,
        )

    def get_subparams(self, types: LuaTypes) -> List["LuaParam"]:
        if self.subparams:
            return self.subparams

        # Many times a parameter with a custom class type will be optional, so the type
        # string will start with "nil|"
        search_type = self.type
        if search_type.startswith("nil|"):
            search_type = search_type[4:]

        cls = types.classes.get(search_type)
        if cls is None:
            return []
        return cls.convert_to_subparams()


@dataclass
class LuaReturn:
    type: str
    desc: str = ""

    @classmethod
    def from_parser(cls, p):
        name, *desc = p.as_list()
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
).set_parse_action(lambda p: "".join(p.as_list()))
lua_func_param = (
    Opt(White()) + ("..." | varname) + ":" + Opt(White()) + lua_type + Opt(White())
).set_parse_action(lambda p: "".join(p.as_list()))
lua_func = (
    Keyword("fun")
    + "("
    + Opt(delimitedList(lua_func_param, combine=True))
    + ")"
    + Opt((":") + Opt(White()) + lua_type)
).set_parse_action(lambda p: "".join(p.as_list()))
non_union_types = lua_list | lua_table | lua_func | primitive_type
union_type = delimitedList(non_union_types, delim="|").set_parse_action(
    lambda p: "|".join(p.as_list())
)
lua_type <<= union_type | non_union_types

tag = Forward()
subparam = (
    Suppress(LineStart())
    + Suppress(White())
    + varname.set_results_name("name")
    + Opt(Literal("?")).set_results_name("optional")
    + lua_type.set_results_name("type")
    + Opt(Regex(".+").set_results_name("desc"))
    + Suppress(LineEnd())
).set_parse_action(LuaParam.from_parser)
tag_param = (
    Suppress("@param")
    + varname.set_results_name("name")
    + Opt(Literal("?")).set_results_name("optional")
    + lua_type.set_results_name("type")
    + Opt(Regex(".+").set_results_name("desc"))
    + Suppress(LineEnd())
    + ZeroOrMore(subparam).set_results_name("subparams")
).set_parse_action(LuaParam.from_parser)
tag_private = (Keyword("@private") + Suppress(LineEnd())).set_results_name("private")
tag_deprecated = (Keyword("@deprecated") + Suppress(LineEnd())).set_results_name(
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
    .set_results_name("example")
    .set_parse_action(lambda p: "".join(p.as_list()))
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
    .set_results_name("note")
    .set_parse_action(lambda p: "".join(p.as_list()))
)
tag_return = (
    Suppress("@return") + lua_type + Regex(".*").setName("desc") + Suppress(LineEnd())
).set_parse_action(LuaReturn.from_parser)
summary = Regex(r"^[^@].+").set_results_name("summary") + Suppress(LineEnd())

tag <<= tag_param | tag_private | tag_return | tag_example | tag_note | tag_deprecated

annotation = Opt(summary) + ZeroOrMore(tag) + Suppress(ZeroOrMore(White()))

scope = (
    Keyword("private") | Keyword("protected") | Keyword("package") | Keyword("public")
).set_parse_action(lambda p: Scope[p[0].upper()])
lua_field = (
    Suppress("@field")
    + (
        (
            Suppress("[")
            + lua_type.set_results_name("key_type")
            + Suppress("]")
            + lua_type.set_results_name("type")
            + Regex(".*").set_results_name("desc")
        )
        | (
            scope.set_results_name("scope")
            + varname.set_results_name("name")
            + lua_type.set_results_name("type")
            + Regex(".*").set_results_name("desc")
        )
        | (
            varname.set_results_name("name")
            + lua_type.set_results_name("type")
            + Regex(".*").set_results_name("desc")
        )
    )
    + Suppress(LineEnd())
).set_parse_action(LuaField.from_parser)

lua_class = (
    Suppress("@class")
    + Suppress(Opt("(exact)"))
    + Regex(r"[^\s:]+").set_results_name("name")
    + Opt(Suppress(":") + Regex(r"\S+").set_results_name("parent"))
    + Suppress(LineEnd())
    + OneOrMore(lua_field).set_results_name("fields")
)
