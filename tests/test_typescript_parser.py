from graphrag.parser.factory import parse_file


def test_parse_typescript_extracts_classes() -> None:
    parsed = parse_file("tests/fixtures/sample.ts")
    assert parsed.language == "typescript"
    class_names = {item.name for item in parsed.classes}
    assert "DataService" in class_names
    assert "FileService" in class_names


def test_parse_typescript_extracts_class_methods() -> None:
    parsed = parse_file("tests/fixtures/sample.ts")
    method_map = {(item.name, item.class_name): item for item in parsed.methods}
    assert ("process", "DataService") in method_map
    assert ("formatOutput", "DataService") in method_map
    assert ("readFile", "FileService") in method_map


def test_parse_typescript_extracts_top_level_functions() -> None:
    parsed = parse_file("tests/fixtures/sample.ts")
    top_level = {item.name for item in parsed.methods if item.class_name is None}
    assert "topLevelHelper" in top_level


def test_parse_typescript_fqns_are_correct() -> None:
    parsed = parse_file("tests/fixtures/sample.ts")
    method_map = {item.name: item for item in parsed.methods if item.class_name == "DataService"}
    assert method_map["process"].fqn == "tests.fixtures.sample.DataService.process"


def test_parse_typescript_extracts_imports() -> None:
    parsed = parse_file("tests/fixtures/sample.ts")
    assert len(parsed.imports) >= 1


def test_parse_typescript_extracts_call_edges() -> None:
    parsed = parse_file("tests/fixtures/sample.ts")
    method_map = {item.name: item for item in parsed.methods if item.class_name == "DataService"}
    callee_names = {call.callee_name for call in method_map["process"].calls}
    assert any("formatOutput" in name for name in callee_names)


def test_parse_typescript_signature_not_empty() -> None:
    parsed = parse_file("tests/fixtures/sample.ts")
    for method in parsed.methods:
        assert method.signature != "", f"Empty signature for {method.fqn}"


def test_parse_typescript_source_code_not_empty() -> None:
    parsed = parse_file("tests/fixtures/sample.ts")
    for method in parsed.methods:
        assert method.source_code != "", f"Empty source_code for {method.fqn}"


def test_parse_javascript_extracts_classes() -> None:
    parsed = parse_file("tests/fixtures/sample.js")
    assert parsed.language == "javascript"
    class_names = {item.name for item in parsed.classes}
    assert "Calculator" in class_names
    assert "FileHelper" in class_names


def test_parse_javascript_extracts_class_methods() -> None:
    parsed = parse_file("tests/fixtures/sample.js")
    method_map = {(item.name, item.class_name): item for item in parsed.methods}
    assert ("add", "Calculator") in method_map
    assert ("validate", "Calculator") in method_map


def test_parse_javascript_extracts_top_level_functions() -> None:
    parsed = parse_file("tests/fixtures/sample.js")
    top_level = {item.name for item in parsed.methods if item.class_name is None}
    assert "formatResult" in top_level


def test_parse_javascript_call_edges() -> None:
    parsed = parse_file("tests/fixtures/sample.js")
    method_map = {item.name: item for item in parsed.methods if item.class_name == "Calculator"}
    callee_names = {call.callee_name for call in method_map["add"].calls}
    assert any("validate" in name for name in callee_names)
