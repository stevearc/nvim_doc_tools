import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Type

from pyparsing import (
    Combine,
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
    delimited_list,
    nums,
)

FN_RE = re.compile(r"^M\.(\w+)\s*=|^function ([A-Z][A-Za-z0-9_:\.]*)\s*\(")


@dataclass
class LuaTypes:
    files: Dict[str, "LuaFile"] = field(default_factory=dict)
    classes: Dict[str, "LuaClass"] = field(default_factory=dict)
    aliases: Dict[str, "LuaAlias"] = field(default_factory=dict)

    def add_file(self, filename: str, file: "LuaFile"):
        self.files[filename] = file
        for c in file.classes:
            self.classes[c.name] = c
        for a in file.aliases:
            self.aliases[a.name] = a

    def get_enum_values(self, search_type: str) -> List["AliasValue"]:
        # Many times a parameter with a custom class type will be optional, so the type
        # string will start with "nil|"
        if search_type.startswith("nil|"):
            search_type = search_type[4:]

        alias = self.aliases.get(search_type)
        if alias is not None:
            return alias.values

        return []


@dataclass
class LuaFile:
    functions: List["LuaFunc"] = field(default_factory=list)
    classes: List["LuaClass"] = field(default_factory=list)
    aliases: List["LuaAlias"] = field(default_factory=list)
    errors: List["ParseError"] = field(default_factory=list)


@dataclass
class ParseError:
    error: Exception
    lines: List[str]

    def __str__(self):
        return f"{self.error}\n{''.join(self.lines)}"


@dataclass
class LuaClass:
    name: str
    desc: str = ""
    # If true, the class should not be exploded in parameter documentation
    opaque: bool = False
    parent: Optional[str] = None
    fields: List["LuaField"] = field(default_factory=list)

    @classmethod
    def parse_lines(cls, lines: List[str]) -> "LuaClass":
        # Strip off the leading comment
        lines = [line[3:] for line in lines]
        desc_lines = []
        while lines and not lines[0].startswith("@"):
            desc_lines.append(lines.pop(0))
        p = lua_class.parseString("".join(lines), parseAll=True)
        return cls.from_parser(p, "".join(desc_lines))

    @classmethod
    def from_parser(
        cls: Type["LuaClass"], parse_result: ParseResults, desc: str
    ) -> "LuaClass":
        return cls(
            parse_result.get("name"),
            desc,
            opaque=parse_result.get("opaque"),
            parent=parse_result.get("parent"),
            fields=parse_result.get("fields").as_list(),
        )

    def convert_to_subparams(self) -> List["LuaParam"]:
        params: List["LuaParam"] = []
        if self.opaque:
            return params
        for fld in self.fields:
            if fld.name and fld.is_public:
                params.append(
                    LuaParam(
                        fld.name,
                        fld.type,
                        desc=fld.desc,
                    )
                )
        return params


ALIAS_VAL_RE = re.compile(r"^\| '([^']+)'(?: # (.+))?$")


@dataclass
class LuaAlias:
    name: str
    values: List["AliasValue"] = field(default_factory=list)

    @classmethod
    def parse_lines(cls, lines: List[str]) -> Optional["LuaAlias"]:
        # Strip off the leading comment
        lines = [line[3:] for line in lines]
        name = lines.pop(0).split()[1]
        values = []
        for line in lines:
            match = ALIAS_VAL_RE.match(line)
            if not match:
                return None
            values.append(AliasValue(match.group(1), match.group(2) or ""))

        if not values:
            return None
        return cls(name, values)

    def convert_to_subparams(self) -> List["LuaParam"]:
        params = []
        for val in self.values:
            params.append(
                LuaParam(
                    "",
                    val.value,
                    desc=val.desc,
                )
            )
        return params


@dataclass
class AliasValue:
    value: str
    desc: str = ""


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
        ptype = parse_result["type"]
        if "optional" in parse_result:
            ptype = "nil|" + ptype
        return cls(
            name=parse_result.get("name"),
            type=ptype,
            key_type=parse_result.get("key_type"),
            desc=parse_result.get("desc", ""),
            scope=parse_result.get("scope"),
        )

    @property
    def is_public(self) -> bool:
        return self.scope is None or self.scope == Scope.PUBLIC


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
    def parse_annotation(cls, name: str, lines: List[str]) -> "LuaFunc":
        # Strip off the leading comment
        lines = [line[3:] for line in lines]
        p = annotation.parseString("".join(lines), parseAll=True)
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

        clazz = types.classes.get(search_type)
        if clazz is not None:
            return clazz.convert_to_subparams()

        return []


@dataclass
class LuaReturn:
    type: str
    desc: str = ""

    @classmethod
    def from_parser(cls, p):
        name, *desc = p.as_list()
        return cls(name, "".join(desc))


def combined_list(expr, delim=","):
    delimited_list_expr = expr + (delim + Opt(White()) + expr)[None, None]
    return Combine(delimited_list_expr, adjacent=False)


ParserElement.setDefaultWhitespaceChars(" \t")

varname = Word(alphas + "_", alphanums + "_")
lua_type = Forward()
primitive_type = (
    Keyword("nil")
    | Keyword("string")
    | Keyword("integer")
    | Keyword("boolean")
    | Keyword("number")
    | Keyword("table")
    | QuotedString('"', unquote_results=False)
    | Word(nums)
    | Keyword("any")
    | Regex(r"\w+(\.[\w]+)+(\[\])?")
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
lua_table_keyval = varname + Opt(Literal("?")) + ":" + Opt(White()) + lua_type
table_literal = Combine(
    Literal("{") + combined_list(lua_table_keyval) + Literal("}"), adjacent=False
)

lua_func_param = (
    Opt(White())
    + (Literal("...") | varname)
    + Opt("?")
    + ":"
    + Opt(White())
    + lua_type
    + Opt(White())
).set_parse_action(lambda p: "".join(p.as_list()))
lua_func = (
    Keyword("fun")
    + "("
    + Opt(delimited_list(lua_func_param, combine=True))
    + ")"
    + Opt((":") + Opt(White()) + lua_type)
).set_parse_action(lambda p: "".join(p.as_list()))
non_union_types = lua_list | lua_table | table_literal | lua_func | primitive_type
union_type = delimited_list(non_union_types, delim="|").set_parse_action(
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
    + (Literal("...") | varname).set_results_name("name")
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
            + Opt(Literal("?")).set_results_name("optional")
            + lua_type.set_results_name("type")
            + Regex(".*").set_results_name("desc")
        )
        | (
            varname.set_results_name("name")
            + Opt(Literal("?")).set_results_name("optional")
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
    + Opt(Keyword("@opaque") + Suppress(LineEnd())).set_results_name("opaque")
    + OneOrMore(lua_field).set_results_name("fields")
)
