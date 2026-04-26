from utils import add_numbers, format_result


def run() -> str:
    total = add_numbers(1, 2)
    return format_result(total)
