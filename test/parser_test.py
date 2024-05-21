def test_parse_function() -> None:
    from .. import apidoc

    file = apidoc._parse_lines(
        """
---This is a function
---@param varnil nil
---@param varstring string this is a string
---@param varoptstring? string this is an optional string
---@param varinteger integer this is a integer
---@param varboolean boolean this is a boolean
---@param varnumber number this is a number
---@param vartable table this is a table
---@param varany any this is any value
---@param varuser user.Type this is a user type
---@param varstrlist string[]
---@param varanylist any[]
---@param vartblmap table<string, integer[]>
---@param varfun fun()
---@param varfunarg fun(arg1: string)
---@param varfunfull fun(arg1: string): integer
---@param varfunvarargs fun(...: any)
---@param varunion nil|string
---@param varstrunion "a"|"b"
---@param varnesttable table
---    prop1 string a nested table prop
---    prop2 integer[]
---@private
---@deprecated
---@return string
---@return user.Type a user type
function M.myfunc()
end
""".splitlines(
            keepends=True
        )
    )
    funcs = file.functions

    assert len(funcs) == 1
    func = funcs[0]
    assert func.name == "M.myfunc"
    assert func.private
    assert func.deprecated
    assert func.params == [
        apidoc.LuaParam("varnil", "nil"),
        apidoc.LuaParam("varstring", "string", "this is a string"),
        apidoc.LuaParam("varoptstring", "nil|string", "this is an optional string"),
        apidoc.LuaParam("varinteger", "integer", "this is a integer"),
        apidoc.LuaParam("varboolean", "boolean", "this is a boolean"),
        apidoc.LuaParam("varnumber", "number", "this is a number"),
        apidoc.LuaParam("vartable", "table", "this is a table"),
        apidoc.LuaParam("varany", "any", "this is any value"),
        apidoc.LuaParam("varuser", "user.Type", "this is a user type"),
        apidoc.LuaParam("varstrlist", "string[]"),
        apidoc.LuaParam("varanylist", "any[]"),
        apidoc.LuaParam("vartblmap", "table<string, integer[]>"),
        apidoc.LuaParam("varfun", "fun()"),
        apidoc.LuaParam("varfunarg", "fun(arg1: string)"),
        apidoc.LuaParam("varfunfull", "fun(arg1: string): integer"),
        apidoc.LuaParam("varfunvarargs", "fun(...: any)"),
        apidoc.LuaParam("varunion", "nil|string"),
        apidoc.LuaParam("varstrunion", '"a"|"b"'),
        apidoc.LuaParam(
            "varnesttable",
            "table",
            subparams=[
                apidoc.LuaParam("prop1", "string", "a nested table prop"),
                apidoc.LuaParam("prop2", "integer[]"),
            ],
        ),
    ]
    assert func.returns == [
        apidoc.LuaReturn("string"),
        apidoc.LuaReturn("user.Type", "a user type"),
    ]


def test_parse_field() -> None:
    from .. import parser

    field = parser.lua_field.parseString("@field fld_simple integer", parseAll=True)[0]
    assert field is not None
    assert field.name == "fld_simple"
    assert field.type == "integer"
    assert field.scope is None
    assert field.desc == ""

    field = parser.lua_field.parseString(
        "@field private fld_scoped integer my desc", parseAll=True
    )[0]
    assert field is not None
    assert field.name == "fld_scoped"
    assert field.type == "integer"
    assert field.scope == parser.Scope.PRIVATE
    assert field.desc == "my desc"

    field = parser.lua_field.parseString(
        "@field [string] integer my desc", parseAll=True
    )[0]
    assert field is not None
    assert field.name is None
    assert field.key_type == "string"
    assert field.type == "integer"
    assert field.desc == "my desc"


def test_parse_class() -> None:
    from .. import parser

    obj = parser.LuaClass.parse_lines(
        """
---@class test.Class
---@field fld_simple string
---@field private fld_scoped integer
""".splitlines(
            keepends=True
        )
    )

    assert obj is not None
    assert obj.name == "test.Class"
    assert obj.parent is None
    assert obj.fields == [
        parser.LuaField(name="fld_simple", type="string"),
        parser.LuaField(name="fld_scoped", type="integer", scope=parser.Scope.PRIVATE),
    ]

    obj = parser.LuaClass.parse_lines(
        """
---@class test.Class: test.Parent
---@field fld_simple string
""".splitlines(
            keepends=True
        )
    )

    assert obj is not None
    assert obj.name == "test.Class"
    assert obj.parent == "test.Parent"
    assert obj.fields == [
        parser.LuaField(name="fld_simple", type="string"),
    ]
