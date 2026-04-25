import os
from pathlib import Path


class Alpha:
    def method_one(self) -> str:
        return "alpha"

    def method_two(self, value: int) -> int:
        return value + 1


class Beta:
    def run(self) -> bool:
        return True

    def stop(self) -> bool:
        return False


def top_level_one() -> str:
    return os.path.basename(Path("one").as_posix())


def top_level_two(number: int) -> int:
    return number * len(Path("xy").name)
