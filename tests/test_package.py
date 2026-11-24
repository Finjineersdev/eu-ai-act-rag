from pathlib import Path

import actrag
from actrag.ingest import DATA


def test_data_ships_inside_package():
    assert Path(actrag.__file__).resolve().parent / "data" == DATA
    for name in ("corpus.jsonl", "corpus_meta.json", "index.npz"):
        assert (DATA / name).is_file()
