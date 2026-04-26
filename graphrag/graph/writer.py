"""Neo4j writer for parsed repository metadata."""

import os
from datetime import UTC, datetime

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase, Transaction

from graphrag.graph.repo_index import RepoIndex
from graphrag.graph.resolver import CallResolver
from graphrag.parser.factory import CallInfo, ParsedFile
from graphrag.schema.models import ClassNode, MethodNode

load_dotenv()


class Neo4jWriter:
    """Persist parsed file structures into Neo4j."""

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        repo_index: RepoIndex | None = None,
    ) -> None:
        self._driver: Driver = GraphDatabase.driver(uri, auth=(username, password))
        self._repo_prefix = os.getenv("REPO_ROOT_PATH", "").replace("\\", "/").strip("./").replace("/", ".")
        self._repo_index = repo_index or RepoIndex()

    def ingest_file(self, parsed_file: ParsedFile) -> None:
        """Write the complete hierarchy for one parsed file into Neo4j."""
        self._repo_index.register_file(parsed_file)
        import_map = self._repo_index.build_import_map(parsed_file)
        resolver = CallResolver(
            known_fqns=self._repo_index.all_fqns,
            import_map=import_map,
        )

        with self._driver.session() as session:
            with session.begin_transaction() as tx:
                self._write_folder(tx, parsed_file.folder.path, parsed_file.folder.name)
                self._write_file(tx, parsed_file)

                class_fqn_by_name = {class_info.name: class_info.fqn for class_info in parsed_file.classes}
                for class_info in parsed_file.classes:
                    self._write_class(
                        tx=tx,
                        class_node=ClassNode(
                            fqn=class_info.fqn,
                            name=class_info.name,
                            file=parsed_file.path,
                            line=class_info.line,
                            language=parsed_file.language,
                            is_interface=False,
                            is_abstract=False,
                        ),
                        file_path=parsed_file.path,
                    )

                for method in parsed_file.methods:
                    method_node = MethodNode(
                        fqn=method.fqn,
                        name=method.name,
                        file=parsed_file.path,
                        line=method.line,
                        signature=method.signature,
                        source_code=method.source_code,
                        language=parsed_file.language,
                        is_dynamic=False,
                    )
                    parent_fqn = class_fqn_by_name.get(method.class_name or "")
                    self._write_method(
                        tx=tx,
                        method_node=method_node,
                        parent_fqn=parent_fqn or "",
                        file_path=parsed_file.path,
                    )
                    self._write_call_edges(
                        tx=tx,
                        method_fqn=method.fqn,
                        calls=method.calls,
                        resolver=resolver,
                    )

                self._write_imports(tx, parsed_file)
                tx.commit()

    def close(self) -> None:
        """Close the Neo4j driver."""
        self._driver.close()

    def _write_folder(self, tx: Transaction, folder_path: str, folder_name: str) -> None:
        tx.run(
            "MERGE (:Folder {path: $path, name: $name})",
            path=folder_path,
            name=folder_name,
        )

    def _write_file(self, tx: Transaction, parsed_file: ParsedFile) -> None:
        tx.run(
            """
            MERGE (f:File {path: $path})
            SET f.language = $language,
                f.checksum = $checksum,
                f.module_name = $module_name,
                f.last_parsed = $last_parsed
            """,
            path=parsed_file.path,
            language=parsed_file.language,
            checksum=parsed_file.checksum,
            module_name=parsed_file.module_name,
            last_parsed=datetime.now(tz=UTC).isoformat(),
        )
        tx.run(
            """
            MATCH (folder:Folder {path: $folder_path})
            MATCH (file:File {path: $file_path})
            MERGE (folder)-[:CONTAINS]->(file)
            """,
            folder_path=parsed_file.folder.path,
            file_path=parsed_file.path,
        )

    def _write_class(self, tx: Transaction, class_node: ClassNode, file_path: str) -> None:
        tx.run(
            """
            MERGE (c:Class {fqn: $fqn})
            SET c.name = $name,
                c.file = $file,
                c.line = $line,
                c.language = $language,
                c.is_interface = $is_interface,
                c.is_abstract = $is_abstract
            """,
            fqn=class_node.fqn,
            name=class_node.name,
            file=class_node.file,
            line=class_node.line,
            language=class_node.language,
            is_interface=class_node.is_interface,
            is_abstract=class_node.is_abstract,
        )
        tx.run(
            """
            MATCH (f:File {path: $file_path})
            MATCH (c:Class {fqn: $fqn})
            MERGE (f)-[:CONTAINS]->(c)
            """,
            file_path=file_path,
            fqn=class_node.fqn,
        )

    def _write_method(
        self,
        tx: Transaction,
        method_node: MethodNode,
        parent_fqn: str,
        file_path: str,
    ) -> None:
        tx.run(
            """
            MERGE (m:Method {fqn: $fqn})
            SET m.name = $name,
                m.file = $file,
                m.line = $line,
                m.signature = $signature,
                m.source_code = $source_code,
                m.language = $language,
                m.is_dynamic = $is_dynamic
            """,
            fqn=method_node.fqn,
            name=method_node.name,
            file=method_node.file,
            line=method_node.line,
            signature=method_node.signature,
            source_code=method_node.source_code,
            language=method_node.language,
            is_dynamic=method_node.is_dynamic,
        )

        if parent_fqn:
            tx.run(
                """
                MATCH (parent:Class {fqn: $parent_fqn})
                MATCH (m:Method {fqn: $fqn})
                MERGE (parent)-[:CONTAINS]->(m)
                """,
                parent_fqn=parent_fqn,
                fqn=method_node.fqn,
            )
            return

        tx.run(
            """
            MATCH (f:File {path: $file_path})
            MATCH (m:Method {fqn: $fqn})
            MERGE (f)-[:CONTAINS]->(m)
            """,
            file_path=file_path,
            fqn=method_node.fqn,
        )

    def _write_call_edges(
        self,
        tx: Transaction,
        method_fqn: str,
        calls: list[CallInfo],
        resolver: CallResolver,
    ) -> None:
        for call in calls:
            resolved_call = resolver.resolve(callee_name=call.callee_name, line=call.line)
            tx.run(
                """
                MERGE (caller:Method {fqn: $caller_fqn})
                MERGE (callee:Method {fqn: $callee_fqn})
                MERGE (caller)-[r:CALLS]->(callee)
                SET r.line = $line,
                    r.confidence = $confidence,
                    r.resolved = $resolved
                """,
                caller_fqn=method_fqn,
                callee_fqn=resolved_call.callee_fqn,
                line=resolved_call.line,
                confidence=resolved_call.confidence,
                resolved=resolved_call.resolved,
            )

    def _parse_import_entry(self, import_text: str) -> tuple[str, list[str]]:
        if import_text.startswith("from "):
            _, remainder = import_text.split("from ", maxsplit=1)
            module, symbols_part = remainder.split(" import ", maxsplit=1)
            symbols = [symbol.strip() for symbol in symbols_part.split(",") if symbol.strip()]
            return module.strip(), symbols
        if import_text.startswith("import "):
            raw_modules = [part.strip() for part in import_text.replace("import ", "", 1).split(",")]
            module = raw_modules[0].split(" as ")[0].strip()
            return module, []
        return import_text.strip(), []

    def _write_imports(self, tx: Transaction, parsed_file: ParsedFile) -> None:
        module_prefix = self._repo_prefix or parsed_file.module_name.split(".")[0]

        for import_text in parsed_file.imports:
            module_name, symbols = self._parse_import_entry(import_text)
            is_external = not module_name.startswith(module_prefix)
            if is_external:
                tx.run(
                    """
                    MERGE (p:Package {name: $module_name})
                    WITH p
                    MATCH (f:File {path: $file_path})
                    MERGE (f)-[:IMPORTS {symbols: $symbols}]->(p)
                    """,
                    module_name=module_name,
                    file_path=parsed_file.path,
                    symbols=symbols,
                )
            else:
                target_path = f"{module_name.replace('.', '/')}.py"
                tx.run(
                    """
                    MATCH (f:File {path: $file_path})
                    MERGE (target:File {path: $target_path})
                    MERGE (f)-[:IMPORTS {symbols: $symbols}]->(target)
                    """,
                    file_path=parsed_file.path,
                    target_path=target_path,
                    symbols=symbols,
                )

