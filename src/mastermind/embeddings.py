"""Offline CPU-only E5 inference from the verified release inventory."""
import hashlib
import json
import threading

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

    def chunks(self, text):
        if self.tokenizer is None:
            raise DomainError("EMBEDDINGS_UNAVAILABLE", "The offline tokenizer is unavailable.", 503)
        with self.lock:
            # Offsets refer to canonical characters; repeated prefix/special tokens
            # leave room below the 512-token model boundary for every passage.
            self.tokenizer.no_truncation()
            try:
                encoded = self.tokenizer.encode(text, add_special_tokens=False)
            finally:
                self.tokenizer.enable_truncation(max_length=512)
            return [{"start": encoded.offsets[i][0], "end": encoded.offsets[min(i+479, len(encoded.ids)-1)][1]}
                    for i in range(0, len(encoded.ids), 480)]
