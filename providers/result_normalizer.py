import json  # used to format provider results as readable JSON text


def normalize(results: list[dict]) -> str:
    return json.dumps(results, indent=2, ensure_ascii=False)  # convert list of results into formatted text
