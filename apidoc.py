import os
import re
from typing import Callable, Iterable, List

from .parser import LuaClass, LuaField, LuaFile, LuaFunc, LuaParam, LuaReturn, LuaTypes

FN_RE = re.compile(r"^M\.(\w+)\s*=|^function ([A-Z][A-Za-z0-9_:\.]*)\s*\(")

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


def _parse_lines(lines: Iterable[str]) -> "LuaFile":
    funcs = []
    classes = []
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
            else:
                c = LuaClass.parse_lines(chunk)
                if c is not None:
                    classes.append(c)

            chunk = []
    return LuaFile(
        functions=funcs,
        classes=classes,
    )


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
