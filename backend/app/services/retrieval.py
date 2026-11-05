"""질의응답용 경량 검색.

외부 벡터 DB 없이 자료 조각(segment)을 점수화한다.
한국어는 조사가 붙어 단어 단위 일치가 어렵기 때문에 한글은 2글자 단위(bigram), 영문은 단어 단위로 비교한다.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass

from .ai.base import MaterialCtx

CHUNK_CHARS = 900


@dataclass
class Chunk:
    ref: str  # S1, S2 ...
    file: str
    loc: str
    text: str


# 질문에 흔한 의문사·어미 — 내용과 무관하게 아무 문장에나 걸리지 않도록 제외
_Q_STOP = {"무엇", "어떤", "어떻게", "언제", "누구", "어디", "얼마", "이번", "관련", "대한", "내가", "제가", "우리", "알려", "설명", "말하는", "있나", "있는", "하는", "해야"}
_Q_SUFFIX = re.compile(r"(?:인가요|입니까|인가|는가|나요|가요|까요|할까|인지|이란)$")  # 조사는 2글자 비교라 영향이 작아 제거하지 않음


def _grams(text: str) -> list[str]:
    out: list[str] = []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9+\-/.]*|[0-9]+|[가-힣]+", text):
        if re.match(r"[가-힣]", tok):
            tok = _Q_SUFFIX.sub("", tok)
            for stop in _Q_STOP:
                if tok.startswith(stop):
                    tok = tok[len(stop):]
            if len(tok) < 2:
                continue
            out.extend(tok[i : i + 2] for i in range(len(tok) - 1))
        elif len(tok) > 1:
            out.append(tok.lower())
    return out


def _split(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]
    parts, cur = [], ""
    for line in re.split(r"(?<=[.!?。\n])\s*", text):
        if len(cur) + len(line) > CHUNK_CHARS and cur:
            parts.append(cur)
            cur = ""
        cur += line + " "
    if cur.strip():
        parts.append(cur)
    return parts


def build_chunks(materials: list[MaterialCtx]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for m in materials:
        for seg in m.segments:
            for part in _split(seg["text"]):
                chunks.append(Chunk(ref="", file=m.filename, loc=seg["loc"], text=part.strip()))
    return chunks


def search(question: str, materials: list[MaterialCtx], k: int = 6) -> list[Chunk]:
    chunks = build_chunks(materials)
    if not chunks:
        return []
    q = set(_grams(question))
    if not q:
        return []
    docs = [Counter(_grams(c.text)) for c in chunks]
    n = len(docs)
    df = Counter(g for d in docs for g in set(d))
    scored = []
    for c, d in zip(chunks, docs):
        score = sum((1 + math.log(d[g])) * math.log(1 + n / df[g]) for g in q if d[g])
        if score > 0:
            # 짧은 조각이 우연히 높은 점수를 받지 않도록 길이 보정
            scored.append((score / (1 + 0.15 * math.log(1 + len(c.text))), c))
    scored.sort(key=lambda x: -x[0])
    top = [c for _, c in scored[:k]]
    for i, c in enumerate(top, start=1):
        c.ref = f"S{i}"
    return top
