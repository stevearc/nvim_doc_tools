def test_parse_function() -> None:
    from .. import apidoc

    funcs = apidoc._parse_lines(
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
