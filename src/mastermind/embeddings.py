"""Offline CPU-only E5 inference from the verified release inventory."""
import hashlib
import json
import threading
from itertools import pairwise

from .errors import DomainError


class Embeddings:
    def __init__(self, directory, inventory):
        self.directory, self.inventory = directory, inventory
        self.session = self.tokenizer = None
        self.lock = threading.Lock()
        self.failure = None
        self.model_sha = None

    def load(self):
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
            ort.disable_telemetry_events()
            lock = json.loads(self.inventory.read_text("utf-8"))
            if lock["schema"] != "mastermind.embedding.v1" or lock["dimensions"] != 384 or lock["max_tokens"] != 512:
                raise ValueError
            for name in ("model.onnx", "tokenizer.json"):
                path, expected = self.directory / name, lock["files"][name]
                with path.open("rb") as source:
                    if path.stat().st_size != expected["size"] or hashlib.file_digest(source, "sha256").hexdigest() != expected["sha256"]:
                        raise ValueError
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.enable_cpu_mem_arena = False
            options.enable_mem_pattern = False
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            self.session = ort.InferenceSession(str(self.directory / "model.onnx"), sess_options=options,
                                                providers=["CPUExecutionProvider"])
            self.tokenizer = Tokenizer.from_file(str(self.directory / "tokenizer.json"))
            self.tokenizer.enable_truncation(max_length=512)
            self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
            self.model_sha = lock["files"]["model.onnx"]["sha256"]
            self.failure = None
        except (ImportError, OSError, ValueError, KeyError, RuntimeError):
            self.session = self.tokenizer = None
            self.failure = "EMBEDDINGS_UNAVAILABLE"

    def embed(self, texts, *, query=False):
        if not isinstance(texts, list) or not 1 <= len(texts) <= 16 or any(
            not isinstance(text, str) or len(text.encode("utf-8")) > 64*1024 for text in texts
        ):
            raise DomainError("EMBEDDING_LIMIT", "Supply 1–16 bounded text chunks.", 422)
        if self.session is None:
            raise DomainError("EMBEDDINGS_UNAVAILABLE", "The offline embedding model is unavailable.", 503)
        import numpy as np
        with self.lock:
            encoded = self.tokenizer.encode_batch([("query: " if query else "passage: ") + text for text in texts])
            identifiers = np.asarray([item.ids for item in encoded], dtype=np.int64)
            attention = np.asarray([item.attention_mask for item in encoded], dtype=np.int64)
            inputs = {"input_ids": identifiers, "attention_mask": attention,
                      "token_type_ids": np.zeros_like(identifiers)}
            # Bound transient attention tensors while E5 and the local Curator share 2 GiB.
            batches = []
            for offset in range(0, len(texts), 2):
                hidden = self.session.run(None, {item.name: inputs[item.name][offset:offset+2]
                                                 for item in self.session.get_inputs()})[0]
                mask = attention[offset:offset+2, ..., None].astype(np.float32)
                batches.append((hidden*mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1))
            vectors = np.concatenate(batches, axis=0)
            vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
            if vectors.shape != (len(texts), 384) or not np.isfinite(vectors).all():
                raise DomainError("EMBEDDINGS_INVALID", "The offline model returned invalid vectors.", 503)
            return {"model_sha256": self.model_sha, "dimensions": 384, "vectors": vectors.tolist(),
                    "token_counts": [sum(item.attention_mask) for item in encoded]}

    def chunks(self, text, *, sections=None, overlap=0):
        if self.tokenizer is None:
            raise DomainError("EMBEDDINGS_UNAVAILABLE", "The offline tokenizer is unavailable.", 503)
        if type(overlap) is not int or overlap not in {0, 32, 64}:
            raise DomainError('INVALID_CHUNKS', 'Unsupported overlap size.', 422)
        sections = [{'start': 0, 'end': len(text), 'heading': ''}] if sections is None else sections
        if not isinstance(sections, list) or len(sections) > 100000 or any(not isinstance(s, dict) or
                type(s.get('start')) is not int or type(s.get('end')) is not int or
                not 0 <= s['start'] <= s['end'] <= len(text) or not isinstance(s.get('heading', ''), str)
                for s in sections):
            raise DomainError('INVALID_CHUNKS', 'Invalid section boundaries.', 422)
        if any(a['end'] > b['start'] for a, b in pairwise(sections)):
            raise DomainError('INVALID_CHUNKS', 'Section ranges must be ordered and disjoint.', 422)
        with self.lock:
            # Offsets refer to supplied characters; repeated prefix/special tokens
            # leave room below the 512-token model boundary for every passage.
            self.tokenizer.no_truncation()
            try:
                result = []
                for section in sections:
                    base = section['start']
                    body = text[base:section['end']]
                    encoded = self.tokenizer.encode(body, add_special_tokens=False)
                    heading = section.get('heading', '')
                    heading_tokens = self.tokenizer.encode(heading, add_special_tokens=False)
                    if len(heading_tokens.ids) > 64:
                        heading = heading[:heading_tokens.offsets[63][1]]
                    # Includes both E5 prefixes, separators and model special tokens.
                    width = 500-len(self.tokenizer.encode(heading, add_special_tokens=False).ids)
                    i = 0
                    while i < len(encoded.ids):
                        j = min(i+width, len(encoded.ids))
                        # Prefer a complete paragraph; never cross a section.
                        if j < len(encoded.ids):
                            a, b = encoded.offsets[i][0], encoded.offsets[j-1][1]
                            boundary = body.rfind('\n\n', a+(b-a)//2, b)
                            if boundary >= 0:
                                while j > i+overlap+1 and encoded.offsets[j-1][1] > boundary:
                                    j -= 1
                        result.append({'start': base+encoded.offsets[i][0], 'end': base+encoded.offsets[j-1][1],
                                       'heading': heading, 'section_start': base,
                                       'source_start': section.get('source_start', 0),
                                       'source_end': section.get('source_end', len(text))})
                        if j == len(encoded.ids):
                            break
                        i = max(i+1, j-overlap)
                return result
            finally:
                self.tokenizer.enable_truncation(max_length=512)
