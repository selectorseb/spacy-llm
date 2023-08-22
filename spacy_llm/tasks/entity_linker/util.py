import csv
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import spacy
from spacy.pipeline import EntityLinker
from spacy.scorer import Scorer
from spacy.tokens import Span
from spacy.training import Example

from ...compat import Self
from ...ty import FewshotExample
from .task import EntityLinkerTask
from .ty import EntityCandidate


class EntLinkExample(FewshotExample):
    text: str
    mentions_str: str
    mentions: List[str]
    entity_descriptions: List[List[str]]
    entity_ids: List[List[str]]
    solutions: List[str]
    reasons: Optional[List[str]]

    @classmethod
    def generate(cls, example: Example, **kwargs) -> Optional[Self]:
        # Ensure that all entities have their knowledge base IDs set.
        n_ents = len(example.reference.ents)
        n_set_kb_ids = sum([ent.kb_id != 0 for ent in example.reference.ents])
        if n_ents and n_ents != n_set_kb_ids:
            warnings.warn(
                f"Not all entities in this document have their knowledge base IDs set ({n_set_kb_ids} out of "
                f"{n_ents}). Ignoring example:\n{example.reference}"
            )
            return None

        # Assemble example.
        mentions = [ent.text for ent in example.reference.ents]
        # Fetch candidates. If true entity not among candidates: fetch description separately and add manually.
        cands_ents, solutions = kwargs["fetch_entity_info"](example.reference)
        # If we are to use available docs as examples, they have to have KB IDs set and hence available solutions.
        assert all([sol is not None for sol in solutions])

        return EntLinkExample(
            text=EntityLinkerTask.highlight_ents_in_text(example.reference).text,
            mentions_str=", ".join([f"*{mention}*" for mention in mentions]),
            mentions=mentions,
            entity_descriptions=[
                [cand_ent.description for cand_ent in cands_ent]
                for cands_ent in cands_ents
            ],
            entity_ids=[
                [cand_ent.id for cand_ent in cands_ent] for cands_ent in cands_ents
            ],
            solutions=solutions,
            reasons=[""] * len(mentions),
        )


def score(examples: Iterable[Example], **kwargs) -> Dict[str, Any]:
    """Score entity linking accuracy in examples.
    examples (Iterable[Example]): Examples to score.
    RETURNS (Dict[str, Any]): Dict with metric name -> score.
    """
    return Scorer.score_links(examples, negative_labels=[EntityLinker.NIL])


class SpaCyPipelineCandidateSelector:
    """Callable generated by loading and wrapping a spaCy pipeline with an NEL component and a filled knowledge base."""

    def __init__(
        self, nlp_path: Union[Path, str], desc_path: Union[Path, str], top_n: int = 5
    ):
        """
        Loads spaCy pipeline, knowledge base, entity descriptions.
        top_n (int): Top n candidates to include in prompt.
        nlp_path (Union[Path, str]): Path to stored spaCy pipeline.
        desc_path (Union[Path, str]): Path to .csv file with descriptions for entities. Has to have two columns
          with the first one being the entity ID, the second one being the description. The entity ID has to match with
          the entity ID in the stored knowledge base.
        """
        self._nlp = spacy.load(nlp_path)
        if "entity_linker" not in self._nlp.component_names:
            raise ValueError(
                f"'entity_linker' component has to be available in specified pipeline at {nlp_path}, but "
                f"isn't."
            )
        self._entity_linker: EntityLinker = self._nlp.get_pipe("entity_linker")
        self._kb = self._entity_linker.kb
        with open(desc_path) as csvfile:
            self._descs: Dict[str, str] = {}
            for row in csv.reader(csvfile, quoting=csv.QUOTE_ALL, delimiter=";"):
                if len(row) != 2:
                    continue
                self._descs[row[0]] = row[1]

            if len(self._descs) == 0:
                raise ValueError(
                    "Format of CSV file with entity descriptions is wrong. CSV has to be formatted as "
                    "semicolon-delimited CSV with two columns. The first columns has to contain the entity"
                    " ID, the second the entity description."
                )
        self._top_n = top_n

    def __call__(self, mentions: Iterable[Span]) -> Iterable[Iterable[EntityCandidate]]:
        """Retrieves top n candidates using spaCy's entity linker's .get_candidates_batch().
        mentions (Iterable[Span]): Mentions to look up entity candidates for.
        RETURNS (Iterable[Iterable[Entity]]): Top n entity candidates per mention.
        """
        all_cands = self._kb.get_candidates_batch(mentions)
        for cands in all_cands:
            assert isinstance(cands, list)
            cands.sort(key=lambda x: x.prior_prob, reverse=True)

        return [
            [
                EntityCandidate(id=cand.entity_, description=self._descs[cand.entity_])
                for cand in cands[: self._top_n]
            ]
            for cands in all_cands
        ]

    def get_entity_description(self, entity_id: str) -> str:
        if entity_id not in self._descs:
            warnings.warn(
                f"Entity with ID {entity_id} is not in provided descriptions file."
            )

        return self._descs[entity_id]
