import os
from pathlib import Path


class Alpha:
    def method_one(self) -> str:
        return top_level_one()

    def method_two(self, value: int) -> int:
        return self.method_one().count("a") + value + top_level_two(1)


class Beta:
    def run(self) -> bool:
        return bool(os.path.basename(Path("run").as_posix()))

    def stop(self) -> bool:
        return bool(self.run())


def top_level_one() -> str:
    return os.path.basename(Path("one").as_posix())


def top_level_two(number: int) -> int:
    return number * len(Path("xy").name) + len(top_level_one())
