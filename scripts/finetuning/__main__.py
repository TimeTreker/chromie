"""Explicit command line for private local dataset, training and evaluation work."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .common import Rejected, digest, encoded, loads, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Print receipt identities only, never private text")
    inspect.add_argument("receipts", type=Path, nargs="+")
    export = commands.add_parser("export", help="Export reviewed transactions; never mine an answer from a trace")
    export.add_argument("--receipts", type=Path, nargs="+", required=True)
    export.add_argument("--traces", type=Path, nargs="*", default=[])
    export.add_argument("--reviews", type=Path, required=True)
    export.add_argument("--redactions", type=Path, required=True)
    export.add_argument("--salt-file", type=Path, required=True)
    export.add_argument("--output", type=Path)
    export.add_argument("--preview-hashes", action="store_true",
                        help="Compute sanitized packet hashes for local human review; write no content")
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--base", type=Path, required=True)
    preflight.add_argument("--gpu", action="store_true")
    tokens = commands.add_parser("audit-tokens", help="Measure complete prompts and targets before allocating GPU memory")
    tokens.add_argument("--base", type=Path, required=True)
    tokens.add_argument("--dataset", type=Path, required=True)
    tokens.add_argument("--max-length", type=int, default=8192)
    for name in ("train", "merge"):
        sub = commands.add_parser(name)
        sub.add_argument("--base", type=Path, required=True)
        sub.add_argument("--output", type=Path, required=True)
        sub.add_argument("--accept-apache-2", action="store_true", required=True)
        if name == "train":
            sub.add_argument("--dataset", type=Path, required=True)
            sub.add_argument("--role", choices=("planner", "social_cognition", "both"), required=True)
            sub.add_argument("--method", choices=("qlora", "lora"), default="qlora")
            sub.add_argument("--max-length", type=int, default=8192)
            sub.add_argument("--max-steps", type=int, default=200)
            sub.add_argument("--seed", type=int, default=42)
        else:
            sub.add_argument("--run", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--dataset", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--split", choices=("validation", "frozen_test"), default="frozen_test")
    evaluate.add_argument("--url")
    evaluate.add_argument("--model")
    serve = commands.add_parser("serve", help="Print an isolated candidate command; --launch explicitly starts it")
    serve.add_argument("--merged", type=Path, required=True)
    serve.add_argument("--image", required=True, help="Local image ID sha256:... from the current patched SGLang container")
    serve.add_argument("--port", type=int, default=30001)
    serve.add_argument("--launch", action="store_true")
    compare = commands.add_parser("compare")
    for name in ("baseline", "candidate", "review", "output"):
        compare.add_argument("--" + name, type=Path, required=True)
    compare.add_argument("--latency-ratio", type=float, default=1.2)
    args = parser.parse_args()
    # Operational artifacts may contain private input. CLI errors expose codes,
    # never source lines, exception payloads or resolver log previews.
    logging.disable(logging.CRITICAL)
    from .model import offline
    offline()
    try:
        if args.command == "inspect":
            from .dataset import receipts
            from .contracts import STAGES
            known = set().union(*STAGES.values())
            result = [{"receipt_sha256": sha, "stage": row.get("stage") if row.get("stage") in known else "unsupported",
                       "status": row.get("status") if row.get("status") in {"accepted", "failed", "cancelled"} else "unknown",
                       "call_id_sha256": digest(row.get("call_id"))} for sha, row in receipts(args.receipts).items()]
        elif args.command == "export":
            from .dataset import export_cases, prepare, receipts, sanitized_case, trace_index
            sources = receipts(args.receipts)
            reviews = loads(args.reviews.read_text())
            replacements = loads(args.redactions.read_text())
            if args.preview_hashes:
                result = []
                for review in reviews:
                    packet = sanitized_case(review, sources, replacements)
                    result.append({"receipt_sha256": review["receipt_sha256"], "sanitized_sha256": digest(packet)})
            else:
                if args.output is None:
                    raise Rejected("new_output_directory_required")
                traces = trace_index(args.traces)
                cases = [prepare(review, sources, traces, replacements, args.salt_file.read_bytes()) for review in reviews]
                result = export_cases(cases, args.output)
        elif args.command == "preflight":
            from .model import gpu_preflight, verify_base
            result = {"base": verify_base(args.base)}
            if args.gpu:
                result["hardware"] = gpu_preflight()
        elif args.command == "audit-tokens":
            from transformers import AutoTokenizer
            from .dataset import load_dataset
            from .model import tokenize_sample, verify_base
            verify_base(args.base, weights=False)
            load_dataset(args.dataset)
            tokenizer = AutoTokenizer.from_pretrained(str(args.base), local_files_only=True, trust_remote_code=False)
            result = []
            for split in ("train", "validation", "frozen_test"):
                for line in (args.dataset / (split + ".jsonl")).read_text().splitlines():
                    row = loads(line)
                    tokens = tokenize_sample(tokenizer, row, 262144)
                    result.append({"case_id": row["case_id"], "split": split, "stage": row["stage"],
                                   "tokens": len(tokens["input_ids"]),
                                   "target_tokens": sum(token != -100 for token in tokens["labels"]),
                                   "over_limit": len(tokens["input_ids"]) > args.max_length})
            print(encoded(result).decode())
            return 2 if any(row["over_limit"] for row in result) else 0
        elif args.command == "train":
            from .train import train
            train(base=args.base, dataset=args.dataset, output=args.output, role=args.role,
                  method=args.method, max_length=args.max_length, max_steps=args.max_steps, seed=args.seed)
            result = {"status": "training_complete", "promotion_allowed": False}
        elif args.command == "merge":
            from .train import merge
            merge(base=args.base, run=args.run, output=args.output)
            result = {"status": "merged_candidate", "promotion_allowed": False}
        elif args.command == "evaluate":
            from .evaluate import evaluate
            report = evaluate(dataset=args.dataset, output=args.output, split=args.split, url=args.url, model=args.model)
            result = {"passed": report["passed"], "complete": report["complete"], "summary_sha256": digest(report)}
            print(encoded(result).decode())
            return 0 if report["passed"] else 1
        elif args.command == "serve":
            from .serve import command, launch
            argv = command(merged=args.merged, image=args.image, port=args.port)
            if args.launch:
                return launch(argv)
            import shlex
            print(shlex.join(argv))
            return 0
        else:
            from .evaluate import compare
            result = compare(loads(args.baseline.read_text()), loads(args.candidate.read_text()),
                             loads(args.review.read_text()), latency_ratio=args.latency_ratio)
            write_json(args.output, result)
            print(encoded(result).decode())
            return 0 if result["passed"] else 1
        print(encoded(result).decode())
        return 0
    except Exception as exc:
        code = str(exc) if isinstance(exc, Rejected) else "invalid_or_unavailable_artifact: " + type(exc).__name__
        print("finetuning_rejected: " + code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
