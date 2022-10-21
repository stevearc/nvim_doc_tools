"""Utility methods for generating docs"""
import json
import re
import subprocess
import textwrap
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "indent",
    "dedent",
    "replace_section",
    "read_section",
    "wrap",
    "trim_newlines",
    "read_nvim_json",
    "CommandDef",
    "Command",
    "commands_from_json",
]


def indent(lines: List[str], amount: int) -> List[str]:
    ret = []
    for line in lines:
        if not line.endswith("\n"):
            line += "\n"
        if amount >= 0:
            ret.append(" " * amount + line)
        else:
            space = re.match(r"[ \t]+", line)
            if space:
                ret.append(line[min(abs(amount), space.span()[1]) :])
            else:
                ret.append(line)
    return ret


def dedent(lines: List[str], amount: Optional[int] = None) -> List[str]:
    if amount is None:
        amount = len(lines[0])
        for line in lines:
            m = re.match(r"^\s+", line)
            if not m:
                return lines
            amount = min(amount, len(m[0]))
    return [line[amount:] for line in lines]


def replace_section(
    file: str, start_pat: str, end_pat: Optional[str], lines: List[str]
) -> None:
    prefix_lines: List[str] = []
    postfix_lines: List[str] = []
    file_lines = prefix_lines
    found_section = False
    with open(file, "r", encoding="utf-8") as ifile:
        inside_section = False
        for line in ifile:
            if inside_section:
                if end_pat is not None and re.match(end_pat, line):
                    inside_section = False
                    file_lines = postfix_lines
                    file_lines.append(line)
            else:
                if re.match(start_pat, line):
                    inside_section = True
                    found_section = True
                file_lines.append(line)
    if end_pat is None:
        inside_section = False

    if inside_section or not found_section:
        raise Exception(f"could not find file section {start_pat} in {file}")

    all_lines = prefix_lines + lines + postfix_lines
    with open(file, "w", encoding="utf-8") as ofile:
        ofile.write("".join(all_lines))


def read_section(
    filename: str,
    start_pat: str,
    end_pat: str,
    inclusive: Tuple[bool, bool] = (False, False),
) -> List[str]:
    lines = []
    with open(filename, "r", encoding="utf-8") as ifile:
        inside_section = False
        for line in ifile:
            if inside_section:
                if re.match(end_pat, line):
                    if inclusive[1]:
                        lines.append(line)
                    break
                lines.append(line)
            elif re.match(start_pat, line):
                inside_section = True
                if inclusive[0]:
                    lines.append(line)
    return lines


def wrap(
    text: str,
    indent: int = 0,
    width: int = 80,
    line_end: str = "\n",
    sub_indent: Optional[int] = None,
) -> List[str]:
    if sub_indent is None:
        sub_indent = indent
    return [
        line + line_end
        for line in textwrap.wrap(
            text,
            initial_indent=indent * " ",
            subsequent_indent=sub_indent * " ",
            width=width,
        )
    ]


def trim_newlines(lines: List[str]) -> List[str]:
    while lines and lines[0] == "\n":
        lines.pop(0)
    while lines and lines[-1] == "\n":
        lines.pop()
    return lines


def read_nvim_json(lua: str) -> Any:
    cmd = f"nvim --headless --noplugin -u /dev/null -c 'set runtimepath+=.' -c 'lua print(vim.json.encode({lua}))' +qall"
    print(cmd)
    code, txt = subprocess.getstatusoutput(cmd)
    if code != 0:
        raise Exception(f"Error exporting data from nvim: {txt}")
    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        raise Exception(f"Json decode error: {txt}") from e


@dataclass(frozen=True)
class CommandDef:
    desc: str
    count: Optional[int] = None
    nargs: Optional[str] = None
    bang: bool = False


@dataclass(frozen=True)
class Command:
    cmd: str
    defn: CommandDef
    func: str
    args: str = ""
    deprecated: Optional[Dict] = None
    long_desc: str = ""


def commands_from_json(data: Any) -> List["Command"]:
    # TODO is there a way to init dataclasses recursively?
    ret = []
    for cmd in data:
        cmd["defn"] = CommandDef(**cmd["defn"])
        ret.append(Command(**cmd))
    return ret
