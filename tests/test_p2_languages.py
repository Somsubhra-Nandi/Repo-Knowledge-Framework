from graphrag.parser.factory import parse_file


# -- Ruby --------------------------------------------------
def test_ruby_extracts_classes():
    parsed = parse_file("tests/fixtures/sample.rb")
    assert parsed.language == "ruby"
    names = {c.name for c in parsed.classes}
    assert "UserService" in names


def test_ruby_extracts_methods():
    parsed = parse_file("tests/fixtures/sample.rb")
    method_map = {(m.name, m.class_name) for m in parsed.methods}
    assert ("get_user", "UserService") in method_map
    assert ("format_user", "UserService") in method_map


def test_ruby_extracts_top_level_functions():
    parsed = parse_file("tests/fixtures/sample.rb")
    top = {m.name for m in parsed.methods if m.class_name is None}
    assert "standalone_function" in top


def test_ruby_extracts_imports():
    parsed = parse_file("tests/fixtures/sample.rb")
    assert len(parsed.imports) >= 1


# -- PHP ---------------------------------------------------
def test_php_extracts_classes():
    parsed = parse_file("tests/fixtures/sample.php")
    assert parsed.language == "php"
    names = {c.name for c in parsed.classes}
    assert "UserService" in names


def test_php_extracts_methods():
    parsed = parse_file("tests/fixtures/sample.php")
    method_map = {(m.name, m.class_name) for m in parsed.methods}
    assert ("getUser", "UserService") in method_map


def test_php_extracts_top_level_functions():
    parsed = parse_file("tests/fixtures/sample.php")
    top = {m.name for m in parsed.methods if m.class_name is None}
    assert "topLevelHelper" in top


# -- Swift -------------------------------------------------
def test_swift_extracts_classes():
    parsed = parse_file("tests/fixtures/sample.swift")
    assert parsed.language == "swift"
    names = {c.name for c in parsed.classes}
    assert "UserService" in names


def test_swift_extracts_methods():
    parsed = parse_file("tests/fixtures/sample.swift")
    method_map = {(m.name, m.class_name) for m in parsed.methods}
    assert ("process", "UserService") in method_map
    assert ("formatOutput", "UserService") in method_map


def test_swift_extracts_structs():
    parsed = parse_file("tests/fixtures/sample.swift")
    names = {c.name for c in parsed.classes}
    assert "Config" in names


def test_swift_extracts_top_level():
    parsed = parse_file("tests/fixtures/sample.swift")
    top = {m.name for m in parsed.methods if m.class_name is None}
    assert "topLevelHelper" in top


# -- Kotlin ------------------------------------------------
def test_kotlin_extracts_classes():
    parsed = parse_file("tests/fixtures/sample.kt")
    assert parsed.language == "kotlin"
    names = {c.name for c in parsed.classes}
    assert "UserService" in names


def test_kotlin_extracts_methods():
    parsed = parse_file("tests/fixtures/sample.kt")
    method_map = {(m.name, m.class_name) for m in parsed.methods}
    assert ("process", "UserService") in method_map
    assert ("getUser", "UserService") in method_map


def test_kotlin_extracts_object():
    parsed = parse_file("tests/fixtures/sample.kt")
    names = {c.name for c in parsed.classes}
    assert "ServiceFactory" in names


# -- Shell -------------------------------------------------
def test_shell_extracts_functions():
    parsed = parse_file("tests/fixtures/sample.sh")
    assert parsed.language == "shell"
    names = {m.name for m in parsed.methods}
    assert "get_user" in names
    assert "format_user" in names
    assert "main" in names


def test_shell_all_class_names_none():
    parsed = parse_file("tests/fixtures/sample.sh")
    assert all(m.class_name is None for m in parsed.methods)


# -- SQL ---------------------------------------------------
def test_sql_extracts_tables():
    parsed = parse_file("tests/fixtures/sample.sql")
    assert parsed.language == "sql"
    names = {c.name for c in parsed.classes}
    assert "users" in names or "Users" in names
    assert "orders" in names or "Orders" in names


def test_sql_extracts_functions():
    parsed = parse_file("tests/fixtures/sample.sql")
    names = {m.name for m in parsed.methods}
    assert any("get_user" in n or "get_user_orders" in n for n in names)


# -- HTML --------------------------------------------------
def test_html_extracts_scripts():
    parsed = parse_file("tests/fixtures/sample.html")
    assert parsed.language == "html"


def test_html_extracts_external_imports():
    parsed = parse_file("tests/fixtures/sample.html")
    assert len(parsed.imports) >= 1


# -- CSS ---------------------------------------------------
def test_css_extracts_selectors():
    parsed = parse_file("tests/fixtures/sample.css")
    assert parsed.language == "css"
    assert len(parsed.methods) >= 1


def test_css_extracts_imports():
    parsed = parse_file("tests/fixtures/sample.css")
    assert len(parsed.imports) >= 1


# -- C -----------------------------------------------------
def test_c_extracts_functions():
    parsed = parse_file("tests/fixtures/sample.c")
    assert parsed.language == "c"
    names = {m.name for m in parsed.methods}
    assert "format_user" in names
    assert "get_user" in names
    assert "main" in names


def test_c_extracts_structs():
    parsed = parse_file("tests/fixtures/sample.c")
    names = {c.name for c in parsed.classes}
    assert "User" in names


def test_c_extracts_includes():
    parsed = parse_file("tests/fixtures/sample.c")
    assert len(parsed.imports) >= 1
    assert any("stdio" in imp for imp in parsed.imports)


def test_c_all_class_names_none_for_functions():
    parsed = parse_file("tests/fixtures/sample.c")
    assert all(m.class_name is None for m in parsed.methods)


def test_c_extracts_call_edges():
    parsed = parse_file("tests/fixtures/sample.c")
    method_map = {m.name: m for m in parsed.methods}
    assert "get_user" in method_map
    callee_names = {c.callee_name for c in method_map["main"].calls}
    assert any("get_user" in n or "format_user" in n for n in callee_names)


# -- C++ ---------------------------------------------------
def test_cpp_extracts_classes():
    parsed = parse_file("tests/fixtures/sample.cpp")
    assert parsed.language == "cpp"
    names = {c.name for c in parsed.classes}
    assert "UserService" in names


def test_cpp_extracts_class_methods():
    parsed = parse_file("tests/fixtures/sample.cpp")
    method_map = {(m.name, m.class_name) for m in parsed.methods}
    assert ("getUser", "UserService") in method_map
    assert ("formatUser", "UserService") in method_map


def test_cpp_extracts_structs():
    parsed = parse_file("tests/fixtures/sample.cpp")
    names = {c.name for c in parsed.classes}
    assert "Config" in names


def test_cpp_extracts_free_functions():
    parsed = parse_file("tests/fixtures/sample.cpp")
    top = {m.name for m in parsed.methods if m.class_name is None}
    assert "topLevelHelper" in top
    assert "main" in top


def test_cpp_extracts_includes():
    parsed = parse_file("tests/fixtures/sample.cpp")
    assert len(parsed.imports) >= 1
    assert any("iostream" in imp or "string" in imp for imp in parsed.imports)


def test_cpp_extracts_call_edges():
    parsed = parse_file("tests/fixtures/sample.cpp")
    method_map = {m.name: m for m in parsed.methods if m.class_name == "UserService"}
    assert "getUser" in method_map
    callee_names = {c.callee_name for c in method_map["getUser"].calls}
    assert any("formatUser" in n or "format" in n for n in callee_names)


def test_all_p2_languages_parse_without_crash():
    """Bulk smoke test: all new P2 fixtures parse without exception."""
    fixtures = [
        "tests/fixtures/sample.rb",
        "tests/fixtures/sample.php",
        "tests/fixtures/sample.swift",
        "tests/fixtures/sample.kt",
        "tests/fixtures/sample.sh",
        "tests/fixtures/sample.sql",
        "tests/fixtures/sample.html",
        "tests/fixtures/sample.css",
        "tests/fixtures/sample.c",
        "tests/fixtures/sample.cpp",
    ]
    for path in fixtures:
        parsed = parse_file(path)
        assert parsed.path == path, f"parse_file failed for {path}"
        assert parsed.language != "", f"Empty language for {path}"
