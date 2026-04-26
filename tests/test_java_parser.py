from graphrag.parser.factory import parse_file


def test_parse_java_extracts_classes() -> None:
    parsed = parse_file("tests/fixtures/sample.java")
    assert parsed.language == "java"
    class_names = {item.name for item in parsed.classes}
    assert "UserService" in class_names
    assert "HelperService" in class_names


def test_parse_java_fqns_use_package_name() -> None:
    parsed = parse_file("tests/fixtures/sample.java")
    class_map = {item.name: item for item in parsed.classes}
    assert class_map["UserService"].fqn == "com.example.service.UserService"


def test_parse_java_extracts_methods() -> None:
    parsed = parse_file("tests/fixtures/sample.java")
    method_map = {(item.name, item.class_name): item for item in parsed.methods}
    assert ("getUsers", "UserService") in method_map
    assert ("getUserById", "UserService") in method_map
    assert ("buildUserList", "UserService") in method_map
    assert ("formatUser", "UserService") in method_map


def test_parse_java_extracts_constructor() -> None:
    parsed = parse_file("tests/fixtures/sample.java")
    method_map = {(item.name, item.class_name): item for item in parsed.methods}
    assert ("UserService", "UserService") in method_map


def test_parse_java_method_fqns_correct() -> None:
    parsed = parse_file("tests/fixtures/sample.java")
    method_map = {item.name: item for item in parsed.methods if item.class_name == "UserService"}
    assert method_map["getUsers"].fqn == "com.example.service.UserService.getUsers"


def test_parse_java_extracts_imports() -> None:
    parsed = parse_file("tests/fixtures/sample.java")
    assert len(parsed.imports) >= 2
    assert any("java.util.List" in imp for imp in parsed.imports)


def test_parse_java_extracts_call_edges() -> None:
    parsed = parse_file("tests/fixtures/sample.java")
    method_map = {item.name: item for item in parsed.methods if item.class_name == "UserService"}
    callee_names = {call.callee_name for call in method_map["getUserById"].calls}
    assert any("getUsers" in name or "formatUser" in name for name in callee_names)


def test_parse_java_signature_not_empty() -> None:
    parsed = parse_file("tests/fixtures/sample.java")
    for method in parsed.methods:
        assert method.signature != "", f"Empty signature for {method.fqn}"


def test_parse_java_source_code_not_empty() -> None:
    parsed = parse_file("tests/fixtures/sample.java")
    for method in parsed.methods:
        assert method.source_code != "", f"Empty source_code for {method.fqn}"


def test_parse_java_annotations_in_signature() -> None:
    parsed = parse_file("tests/fixtures/UserController.java")
    method_map = {item.name: item for item in parsed.methods}
    assert "getUsers" in method_map
    assert "GetMapping" in method_map["getUsers"].signature


def test_parse_java_controller_class_exists() -> None:
    parsed = parse_file("tests/fixtures/UserController.java")
    class_names = {item.name for item in parsed.classes}
    assert "UserController" in class_names
