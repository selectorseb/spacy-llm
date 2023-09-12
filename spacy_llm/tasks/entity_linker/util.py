import csv
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from spacy.pipeline import EntityLinker
from spacy.scorer import Scorer
from spacy.training import Example

from ...compat import Self
from ...ty import FewshotExample
from .task import EntityLinkerTask

UNAVAILABLE_ENTITY_DESC: str = "This entity doesn't have a description."


class ELExample(FewshotExample):
    text: str
    mentions: List[str]
    entity_descriptions: List[List[str]]
    entity_ids: List[List[str]]
    solutions: List[str]
    reasons: Optional[List[str]]

    @property
    def mentions_str(self) -> str:
        """Returns stringified version of all mentions.
        RETURNS (str): Stringified version of all mentions.
        """
        return ", ".join([f"*{mention}*" for mention in self.mentions])

    @classmethod
    def generate(cls, example: Example, **kwargs) -> Optional[Self]:
        # Check whether all entities have their knowledge base IDs set.
        n_ents = len(example.reference.ents)
        n_set_kb_ids = sum([ent.kb_id != 0 for ent in example.reference.ents])
        if n_ents and n_ents != n_set_kb_ids:
            warnings.warn(
                f"Not all entities in this document have their knowledge base IDs set ({n_set_kb_ids} out of "
                f"{n_ents}). Ignoring {n_set_kb_ids - n_ents} entities in example:\n{example.reference}"
            )
        example.reference.ents = [
            ent for ent in example.reference.ents if ent.kb_id != 0
        ]
        if len(example.reference.ents) == 0:
            return None

        # Assemble example.
        mentions = [ent.text for ent in example.reference.ents]
        # Fetch candidates. If true entity not among candidates: fetch description separately and add manually.
        cands_ents, solutions = kwargs["fetch_entity_info"](example.reference)
        # If we are to use available docs as examples, they have to have KB IDs set and hence available solutions.
        assert all([sol is not None for sol in solutions])

        return ELExample(
            text=EntityLinkerTask.highlight_ents_in_text(example.reference),
            mentions=mentions,
            entity_descriptions=[
                [ent.description for ent in ents] for ents in cands_ents
            ],
            entity_ids=[[ent.id for ent in ents] for ents in cands_ents],
            solutions=solutions,
            reasons=[""] * len(mentions),
        )


def score(examples: Iterable[Example], **kwargs) -> Dict[str, Any]:
    """Score entity linking accuracy in examples.
    examples (Iterable[Example]): Examples to score.
    RETURNS (Dict[str, Any]): Dict with metric name -> score.
    """
    return Scorer.score_links(examples, negative_labels=[EntityLinker.NIL])


def ent_desc_reader_csv(path: Union[Path, str]) -> Dict[str, str]:
    """Instantiates entity description reader with two columns: ID and description.
    path (Union[Path, str]): File path.
    RETURNS (Dict[str, str]): Dict with ID -> description.
    """
    with open(path) as csvfile:
        descs: Dict[str, str] = {}
        for row in csv.reader(csvfile, quoting=csv.QUOTE_ALL, delimiter=";"):
            if len(row) != 2:
                continue
            descs[row[0]] = row[1]

        if len(descs) == 0:
            raise ValueError(
                "Format of CSV file with entity descriptions is wrong. CSV has to be formatted as "
                "semicolon-delimited CSV with two columns. The first columns has to contain the entity"
                " ID, the second the entity description."
            )

    return descs