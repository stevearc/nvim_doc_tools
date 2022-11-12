import json
import re
import subprocess
import textwrap
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .apidoc import LuaFunc, LuaParam, LuaReturn
from .markdown import MD_BOLD_PAT, MD_LINE_BREAK_PAT, MD_LINK_PAT
from .util import Command, indent, read_section, trim_newlines, wrap

__all__ = [
    "VimdocSection",
    "VimdocToc",
    "Vimdoc",
    "vimlen",
    "leftright",
    "format_vimdoc_commands",
    "convert_markdown_to_vimdoc",
    "convert_md_section_to_vimdoc",
    "render_vimdoc_api",
]


class VimdocSection:
    def __init__(
        self,
        name: str,
        tag: str,
        body: Optional[List[str]] = None,
        sep: str = "-",
        width: int = 80,
    ):
        self.name = name
        self.tag = tag
        self.body = body or []
        self.sep = sep
        self.width = width

    def get_body(self) -> List[str]:
        return self.body

    def render(self) -> List[str]:
        lines = [
            self.width * self.sep + "\n",
            leftright(self.name.upper(), f"*{self.tag}*", self.width),
            "\n",
        ]
        lines.extend(trim_newlines(self.get_body()))
        lines.append("\n")
        return lines


class VimdocToc(VimdocSection):
    def __init__(self, name: str, tag: str, width: int = 80):
        super().__init__(name, tag, width=width)
        self.entries: List[Tuple[str, str]] = []
        self.padding = 2

    def get_body(self) -> List[str]:
        lines = []
        for i, (name, tag) in enumerate(self.entries):
            left = self.padding * " " + f"{i+1}. {name.capitalize()}"
            tag_start = self.width - 2 * self.padding - vimlen(tag)
            lines.append(left.ljust(tag_start, ".") + f"|{tag}|\n")
        return lines


class Vimdoc:
    def __init__(self, filename: str, project: str, width: int = 80):
        tags = [project.capitalize(), project, f"{project}.nvim"]
        self.prefix = [f"*{filename}*\n", " ".join(f"*{tag}*" for tag in tags) + "\n"]
        self.sections: List[VimdocSection] = []
        self.project = project
        self.width = width

    def render(self) -> List[str]:
        header = self.prefix[:]
        body = []
        toc = VimdocToc("CONTENTS", f"{self.project}-contents", width=self.width)
        for section in self.sections:
            toc.entries.append((section.name, section.tag))
            body.extend(section.render())
        body.append(self.width * "=" + "\n")
        body.append("vim:tw=80:ts=2:ft=help:norl:syntax=help:\n")
        return header + toc.render() + body


def count_special(base: str, char: str) -> int:
    c = base.count(char)
    return 2 * (c // 2)


def vimlen(string: str) -> int:
    return len(string) - sum([count_special(string, c) for c in "`|*"])


def leftright(left: str, right: str, width: int = 80) -> str:
    spaces = max(1, width - vimlen(left) - vimlen(right))
    return left + spaces * " " + right + "\n"


def format_vimdoc_commands(commands: List[Command]) -> List[str]:
    lines = []
    for command in commands:
        if command.deprecated:
            continue
        cmd = command.cmd
        if command.defn.count:
            cmd = "[count]" + cmd
        if command.defn.bang:
            cmd += "[!]"
        if command.args:
            cmd += " " + command.args
        lines.append(leftright(cmd, f"*:{command.cmd}*"))
        lines.extend(wrap(command.defn.desc, 4))
        if command.long_desc:
            lines.extend(wrap(command.long_desc, 4))
        lines.append("\n")
    return lines


def convert_md_link(match):
    text = match[1]
    dest = match[2]
    if dest.startswith("#"):
        return f"|{dest[1:]}|"
    else:
        return text


def convert_markdown_to_vimdoc(lines: List[str]) -> List[str]:
    while lines[0] == "\n":
        lines.pop(0)
    while lines[-1] == "\n":
        lines.pop()
    i = 0
    code_block = False
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            code_block = not code_block
            if code_block:
                lines[i] = ">\n"
            else:
                lines[i] = "<\n"
        else:
            if code_block:
                lines[i] = 4 * " " + line
            else:
                line = MD_LINK_PAT.sub(convert_md_link, line)
                line = MD_BOLD_PAT.sub(lambda x: x[1], line)
                line = MD_LINE_BREAK_PAT.sub("", line)

                if len(line) > 80:
                    new_lines = wrap(line)
                    lines[i : i + 1] = new_lines
                    i += len(new_lines)
                    continue
                else:
                    lines[i] = line
        i += 1
    return lines


def convert_md_section_to_vimdoc(
    filename: str,
    start_pat: str,
    end_pat: str,
    section_name: str,
    section_tag: str,
    inclusive: Tuple[bool, bool] = (False, False),
) -> "VimdocSection":
    lines = read_section(filename, start_pat, end_pat, inclusive)
    lines = convert_markdown_to_vimdoc(lines)
    return VimdocSection(section_name, section_tag, lines)


def format_vimdoc_returns(returns: List[LuaReturn], indent: int) -> List[str]:
    lines = []
    for r in returns:
        prefix = indent * " "
        line = prefix + f"`{r.type}`" + " "
        sub_indent = min(len(prefix), indent + 2)
        desc = wrap(r.desc, indent=len(line), sub_indent=sub_indent)
        if desc:
            desc[0] = line + desc[0].lstrip()
            lines.extend(desc)
        else:
            lines.append(line.rstrip() + "\n")

    return lines


def format_vimdoc_params(params: List[LuaParam], indent: int) -> List[str]:
    lines = []
    # Ignore params longer than 16 chars. They are outliers and will ruin the formatting
    max_param = (
        max([len(param.name) for param in params if len(param.name) <= 16] or [8]) + 1
    )
    for param in params:
        prefix = (
            indent * " "
            + "{"
            + f"{param.name}"
            + "}".ljust(max_param - len(param.name))
            + " "
        )
        line = prefix + f"`{param.type}`" + " "
        sub_indent = min(len(prefix), max_param + indent + 2)
        desc = wrap(param.desc, indent=len(line), sub_indent=sub_indent)
        if desc:
            desc[0] = line + desc[0].lstrip()
            lines.extend(desc)
        else:
            lines.append(line.rstrip() + "\n")
        if param.subparams:
            lines.extend(format_vimdoc_params(param.subparams, 10))

    return lines


def render_vimdoc_api(project: str, funcs: List[LuaFunc]) -> List[str]:
    lines = []
    for func in funcs:
        if func.private or func.deprecated:
            continue
        args = ", ".join(["{" + param.name + "}" for param in func.params])
        signature = f"{func.name}({args})"
        if func.returns:
            signature += ": " + ", ".join([r.type for r in func.returns])
        lines.append(leftright(signature, f"*{project}.{func.name}*"))
        lines.extend(wrap(func.summary, 4))
        lines.append("\n")
        if func.params:
            lines.append(4 * " " + "Parameters:\n")
            lines.extend(format_vimdoc_params(func.params, 6))

        if any([r.desc for r in func.returns]):
            lines.append(4 * " " + "Returns:\n")
            lines.extend(format_vimdoc_returns(func.returns, 6))

        if func.note:
            lines.append("\n")
            lines.append(4 * " " + "Note:\n")
            lines.extend(indent(func.note.splitlines(), 6))
        if func.example:
            lines.append("\n")
            lines.append(4 * " " + "Examples: >\n")
            lines.extend(indent(func.example.splitlines(), 6))
            lines.append("<\n")
        lines.append("\n")
    return lines
