from graphrag.parser.factory import parse_file


def test_parse_go_extracts_structs() -> None:
    parsed = parse_file("tests/fixtures/sample.go")
    assert parsed.language == "go"
    class_names = {class_info.name for class_info in parsed.classes}
    assert "UserService" in class_names


def test_parse_go_extracts_interfaces() -> None:
    parsed = parse_file("tests/fixtures/sample.go")
    class_names = {class_info.name for class_info in parsed.classes}
    assert "Processor" in class_names


def test_parse_go_extracts_methods_with_receiver() -> None:
    parsed = parse_file("tests/fixtures/sample.go")
    method_map = {(method.name, method.class_name): method for method in parsed.methods}
    assert ("GetUser", "UserService") in method_map
    assert ("formatUser", "UserService") in method_map


def test_parse_go_extracts_top_level_functions() -> None:
    parsed = parse_file("tests/fixtures/sample.go")
    top_level = {method.name for method in parsed.methods if method.class_name is None}
    assert "TopLevelHelper" in top_level
    assert "NewUserService" in top_level
    assert "main" in top_level


def test_parse_go_fqns_use_package_name() -> None:
    parsed = parse_file("tests/fixtures/sample.go")
    method_map = {method.name: method for method in parsed.methods if method.class_name == "UserService"}
    assert method_map["GetUser"].fqn == "main.UserService.GetUser"


def test_parse_go_extracts_imports() -> None:
    parsed = parse_file("tests/fixtures/sample.go")
    assert len(parsed.imports) >= 1


def test_parse_go_extracts_call_edges() -> None:
    parsed = parse_file("tests/fixtures/sample.go")
    method_map = {method.name: method for method in parsed.methods if method.class_name == "UserService"}
    callee_names = {call.callee_name for call in method_map["GetUser"].calls}
    assert any("formatUser" in name for name in callee_names)


def test_parse_go_signature_not_empty() -> None:
    parsed = parse_file("tests/fixtures/sample.go")
    for method in parsed.methods:
        assert method.signature != "", f"Empty signature: {method.fqn}"


def test_parse_go_source_code_not_empty() -> None:
    parsed = parse_file("tests/fixtures/sample.go")
    for method in parsed.methods:
        assert method.source_code != "", f"Empty source_code: {method.fqn}"


def test_parse_rust_extracts_structs() -> None:
    parsed = parse_file("tests/fixtures/sample.rs")
    assert parsed.language == "rust"
    class_names = {class_info.name for class_info in parsed.classes}
    assert "UserService" in class_names
    assert "Config" in class_names


def test_parse_rust_extracts_traits() -> None:
    parsed = parse_file("tests/fixtures/sample.rs")
    class_names = {class_info.name for class_info in parsed.classes}
    assert "Processor" in class_names


def test_parse_rust_extracts_impl_methods() -> None:
    parsed = parse_file("tests/fixtures/sample.rs")
    method_map = {(method.name, method.class_name): method for method in parsed.methods}
    assert ("new", "UserService") in method_map
    assert ("get_user", "UserService") in method_map
    assert ("format_user", "UserService") in method_map


def test_parse_rust_extracts_trait_impl_methods() -> None:
    """process() is from impl Processor for UserService and maps to UserService."""
    parsed = parse_file("tests/fixtures/sample.rs")
    method_map = {(method.name, method.class_name): method for method in parsed.methods}
    assert ("process", "UserService") in method_map


def test_parse_rust_extracts_free_functions() -> None:
    parsed = parse_file("tests/fixtures/sample.rs")
    top_level = {method.name for method in parsed.methods if method.class_name is None}
    assert "top_level_helper" in top_level
    assert "create_map" in top_level


def test_parse_rust_fqns_correct() -> None:
    parsed = parse_file("tests/fixtures/sample.rs")
    method_map = {method.name: method for method in parsed.methods if method.class_name == "UserService"}
    assert method_map["get_user"].fqn == "tests.fixtures.sample.UserService.get_user"


def test_parse_rust_extracts_imports() -> None:
    parsed = parse_file("tests/fixtures/sample.rs")
    assert len(parsed.imports) >= 1
    assert any("std" in import_text for import_text in parsed.imports)


def test_parse_rust_extracts_call_edges() -> None:
    parsed = parse_file("tests/fixtures/sample.rs")
    method_map = {method.name: method for method in parsed.methods if method.class_name == "UserService"}
    callee_names = {call.callee_name for call in method_map["get_user"].calls}
    assert any("format_user" in name for name in callee_names)


def test_parse_rust_signature_not_empty() -> None:
    parsed = parse_file("tests/fixtures/sample.rs")
    for method in parsed.methods:
        assert method.signature != "", f"Empty signature: {method.fqn}"


def test_parse_rust_source_code_not_empty() -> None:
    parsed = parse_file("tests/fixtures/sample.rs")
    for method in parsed.methods:
        assert method.source_code != "", f"Empty source_code: {method.fqn}"
