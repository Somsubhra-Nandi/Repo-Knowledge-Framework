"""In-memory repository index used for call resolution."""

from graphrag.parser.factory import ParsedFile


class RepoIndex:
    """
    In-memory index of all known FQNs and import mappings across the repo.
    Updated incrementally as each file is ingested.
    Used by CallResolver to resolve cross-file calls.
    """

    def __init__(self) -> None:
        self._fqns: set[str] = set()
        self._import_maps: dict[str, dict[str, str]] = {}

    def register_file(self, parsed_file: ParsedFile) -> None:
        """Add all FQNs and import mappings from a newly parsed file."""
        self._fqns.update(class_info.fqn for class_info in parsed_file.classes)
        self._fqns.update(method.fqn for method in parsed_file.methods)
        self._import_maps[parsed_file.path] = self.build_import_map(parsed_file)

    def build_import_map(self, parsed_file: ParsedFile) -> dict[str, str]:
        """
        Build a local name -> module origin map for a specific file.
        """
        mapping: dict[str, str] = {}
        for import_text in parsed_file.imports:
            if import_text.startswith("from "):
                _, remainder = import_text.split("from ", maxsplit=1)
                module_name, symbols_part = remainder.split(" import ", maxsplit=1)
                for symbol_chunk in symbols_part.split(","):
                    symbol = symbol_chunk.strip()
                    if not symbol:
                        continue
                    if " as " in symbol:
                        original, alias = [part.strip() for part in symbol.split(" as ", maxsplit=1)]
                        mapping[alias] = f"{module_name.strip()}.{original}"
                    else:
                        mapping[symbol] = module_name.strip()
            elif import_text.startswith("import "):
                raw_modules = import_text.replace("import ", "", 1)
                for module_chunk in raw_modules.split(","):
                    entry = module_chunk.strip()
                    if not entry:
                        continue
                    if " as " in entry:
                        module_name, alias = [part.strip() for part in entry.split(" as ", maxsplit=1)]
                        mapping[alias] = module_name
                    else:
                        root = entry.split(".", maxsplit=1)[0]
                        mapping[root] = root
        return mapping

    @property
    def all_fqns(self) -> set[str]:
        return set(self._fqns)
