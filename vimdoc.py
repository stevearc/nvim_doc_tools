from typing import List, Optional, Tuple

from .apidoc import LuaClass, LuaField, LuaFunc, LuaParam, LuaReturn, LuaTypes
from .markdown import MD_BOLD_PAT, MD_LINE_BREAK_PAT, MD_LINK_PAT
from .parser import AliasValue
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
    "render_vimdoc_api2",
    "render_vimdoc_classes",
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
            lines.append(left.ljust(tag_start, " ") + f"|{tag}|\n")
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
                lang = line[3:].strip()
                lines[i] = f">{lang}\n"
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


# pylint: disable=W0621
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


# pylint: disable=W0621
def format_vimdoc_params(
    params: List[LuaParam], types: LuaTypes, indent: int
) -> List[str]:
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
            if desc[0].isspace():
                desc.insert(0, line.rstrip())
            else:
                desc[0] = line + desc[0].lstrip()
            lines.extend(desc)
        else:
            lines.append(line.rstrip() + "\n")
        subparams = param.get_subparams(types)
        if subparams:
            lines.extend(format_vimdoc_params(subparams, types, indent + 4))

        alias_vals = types.get_enum_values(param.type)
        if alias_vals:
            lines.extend(format_vimdoc_alias_values(alias_vals, indent + 4))

    return lines


# pylint: disable=W0621
def format_vimdoc_fields(
    fields: List[LuaField], types: LuaTypes, indent: int
) -> List[str]:
    lines = []
    # Ignore fields longer than 16 chars. They are outliers and will ruin the formatting
    max_field = (
        max(
            [
                len(field.name)
                for field in fields
                if field.name is not None and len(field.name) <= 16
            ]
            or [8]
        )
        + 1
    )
    for field in fields:
        if field.name is None or not field.is_public:
            continue
        prefix = (
            indent * " "
            + "{"
            + f"{field.name}"
            + "}".ljust(max_field - len(field.name))
            + " "
        )
        line = prefix + f"`{field.type}`" + " "
        sub_indent = min(len(prefix), max_field + indent + 2)
        desc = wrap(field.desc, indent=len(line), sub_indent=sub_indent)
        if desc:
            if desc[0].isspace():
                desc.insert(0, line.rstrip())
            else:
                desc[0] = line + desc[0].lstrip()
            lines.extend(desc)
        else:
            lines.append(line.rstrip() + "\n")

    return lines


def format_vimdoc_alias_values(params: List[AliasValue], indent: int) -> List[str]:
    lines = []
    # Ignore values longer than 12 chars. They are outliers and will ruin the formatting
    max_param = (
        max([len(val.value) for val in params if len(val.value) <= 12] or [8]) + 1
    )
    for val in params:
        line = indent * " " + f"`{val.value}`" + "".ljust(max_param - len(val.value))
        sub_indent = min(len(line) - 2, max_param + indent)
        desc = wrap(val.desc, indent=len(line), sub_indent=sub_indent)
        if desc:
            desc[0] = line + desc[0].lstrip()
            lines.extend(desc)
        else:
            lines.append(line.rstrip() + "\n")

    return lines


def render_vimdoc_api(project: str, funcs: List[LuaFunc]) -> List[str]:
    return render_vimdoc_api2(project, funcs, LuaTypes())


def render_vimdoc_api2(
    project: str, funcs: List[LuaFunc], types: LuaTypes
) -> List[str]:
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
            lines.extend(format_vimdoc_params(func.params, types, 6))

        if any([r.desc for r in func.returns]):
            lines.append(4 * " " + "Returns:\n")
            lines.extend(format_vimdoc_returns(func.returns, 6))

        if func.note:
            lines.append("\n")
            lines.append(4 * " " + "Note:\n")
            lines.extend(indent(func.note.splitlines(), 6))
        if func.example:
            lines.append("\n")
            lines.append(4 * " " + "Examples: >lua\n")
            lines.extend(indent(func.example.splitlines(), 6))
            lines.append("<\n")
        lines.append("\n")
    return lines


def render_vimdoc_classes(classes: List[LuaClass], types: LuaTypes) -> List[str]:
    lines = []
    for c in classes:
        title = c.name
        if c.parent:
            title += f"extends {c.parent}"
        lines.append(leftright(title, f"*{c.name}*"))
        lines.append("\n")
        if c.desc:
            lines.append(c.desc + "\n")
            lines.append("\n")
        if c.fields:
            lines.append(4 * " " + "Fields:\n")
            lines.extend(format_vimdoc_fields(c.fields, types, 6))
        lines.append("\n")
    return lines
