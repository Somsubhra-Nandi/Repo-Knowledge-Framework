from graphrag.parser.factory import parse_file


def test_parse_file_extracts_python_symbols() -> None:
    parsed = parse_file("tests/fixtures/sample.py")

    assert parsed.path == "tests/fixtures/sample.py"
    assert parsed.language == "python"
    assert len(parsed.classes) == 2

    class_map = {item.name: item for item in parsed.classes}
    assert set(class_map.keys()) == {"Alpha", "Beta"}
    assert class_map["Alpha"].line == 5
    assert class_map["Alpha"].methods == ["method_one", "method_two"]
    assert class_map["Beta"].line == 13
    assert class_map["Beta"].methods == ["run", "stop"]

    method_map = {(item.name, item.class_name): item for item in parsed.methods}
    assert method_map[("method_one", "Alpha")].line == 6
    assert method_map[("method_two", "Alpha")].line == 9
    assert method_map[("run", "Beta")].line == 14
    assert method_map[("stop", "Beta")].line == 17
    assert method_map[("top_level_one", None)].line == 21
    assert method_map[("top_level_two", None)].line == 25

    top_level_functions = [item for item in parsed.methods if item.class_name is None]
    assert {item.name for item in top_level_functions} == {"top_level_one", "top_level_two"}

    assert parsed.imports
    assert "import os" in parsed.imports
    assert "from pathlib import Path" in parsed.imports
