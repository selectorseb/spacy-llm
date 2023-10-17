from typing import Any, Dict, Iterable, List, Optional

from spacy.scorer import Scorer
from spacy.tokens import Doc
from spacy.training import Example

from ...compat import Self
from ...ty import FewshotExample
from .task import LemmaTask


class LemmaExample(FewshotExample[LemmaTask]):
    text: str
    lemmas: List[Dict[str, str]]

    @classmethod
    def generate(cls, example: Example, task: LemmaTask) -> Optional[Self]:
        lemma_dict = [{t.text: t.lemma_} for t in example.reference]
        return cls(text=example.reference.text, lemmas=lemma_dict)


def score(examples: Iterable[Example], **kwargs) -> Dict[str, Any]:
    """Score lemmatization accuracy in examples.
    examples (Iterable[Example]): Examples to score.
    RETURNS (Dict[str, Any]): Dict with metric name -> score.
    """
    return Scorer.score_token_attr(examples, "lemma")


def reduce_shards_to_doc(shards: Iterable[Doc]) -> Doc:
    """Reduces shards to docs for LemmaTask.
    shards (Iterable[Doc]): Shards to reduce to single doc instance.
    RETURNS (Doc): Fused doc instance.
    """
    # todo this is yet a dummy implementation that will only return the first doc shard.
    return list(shards)[0]
