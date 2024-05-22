import os
import re
from typing import Callable, Iterable, List, Optional

from pyparsing import ParseException

from .parser import (
    LuaClass,
    LuaField,
    LuaFile,
    LuaFunc,
    LuaParam,
    LuaReturn,
    LuaTypes,
    ParseError,
)

FN_RE = re.compile(r"^M\.(\w+)\s*=|^function ([A-Z][A-Za-z0-9_:\.]*)\s*\(")
ANNOTATION_RE = re.compile(r"^---(@\w+)")

__all__ = [
    "LuaTypes",
    "LuaFile",
    "LuaClass",
    "LuaField",
    "LuaFunc",
    "LuaParam",
    "LuaReturn",
    "parse_functions",
    "parse_directory",
]


def parse_luadocs(peek: Optional[str], file: LuaFile, lines: List[str]) -> None:
    annotations = set([])
    for line in lines:
        m = ANNOTATION_RE.match(line)
        if m:
            annotations.add(m[1])

    try:
        fn = peek and FN_RE.match(peek)
        if fn and (
            "@param" in annotations or "@return" in annotations or not annotations
        ):
            func = LuaFunc.parse_annotation(fn[1] or fn[2], lines)
            if func is not None:
                func.raw_annotation = lines
                file.functions.append(func)
        elif "@class" in annotations:
            c = LuaClass.parse_lines(lines)
            if c is not None:
                file.classes.append(c)
    except ParseException as e:
        err_lines = [l for l in lines]
        if peek:
            err_lines.append(peek)
        file.errors.append(ParseError(e, err_lines))


def _parse_lines(lines: Iterable[str]) -> "LuaFile":
    file = LuaFile()
    chunk = []
    for line in lines:
        if line.startswith("---"):
            chunk.append(line)
        elif chunk:
            parse_luadocs(line, file, chunk)
            chunk = []
    if chunk:
        parse_luadocs(None, file, chunk)
    return file


def parse_functions(filename: str) -> List[LuaFunc]:
    file = parse_file(filename)
    return file.functions


def parse_directory(directory: str) -> LuaTypes:
    types = LuaTypes()
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".lua"):
                filepath = os.path.join(root, file)
                lua_file = parse_file(filepath)
                relpath = os.path.relpath(filepath, directory)
                types.add_file(relpath, lua_file)

    return types


def parse_file(filename: str) -> LuaFile:
    with open(filename, "r", encoding="utf-8") as ifile:
        return _parse_lines(ifile)


def render_api(
    file: LuaFile, types: LuaTypes, format: Callable[[LuaFunc, LuaTypes], str]
) -> List[str]:
    ret = []
    for func in file.functions:
        if func.private:
            continue
        ret.extend(func.raw_annotation)
        ret.append(format(func, types) + "\n")
    return ret
