from tests.fixtures.sample import Alpha, top_level_one


class Service:
    def __init__(self) -> None:
        self._alpha = Alpha()

    def process(self) -> str:
        result = self._alpha.method_one()
        return top_level_one() + result

    def run_alpha(self) -> int:
        return self._alpha.method_two(42)
