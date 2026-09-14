#!/usr/bin/env python3
"""Compare base and merged LoRA models on the PCB X-ray test dataset."""

import argparse
import gc
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_BASE_MODEL = Path(
    "/Qwen3.6/Hugging-Face/hub/models--Qwen--Qwen3.6-27B/"
    "snapshots/6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"
)
DEFAULT_TUNED_MODEL = Path("/Qwen3.6/Models2")
DEFAULT_DATASET_JSON = Path("/Qwen3.6/LlamaFactory/data/pcb_xray_test.json")
DEFAULT_OUTPUT_DIR = Path("/Qwen3.6/Test2/results")
ELLIPSE_FIELDS = ("center_x", "center_y", "diameter_x", "diameter_y", "angle")


@dataclass
class Sample:
    image_path: Path
    sample_id: str
    user_content: str


def write_json(value: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_dataset_json(dataset_json: Path, limit: int | None) -> list[Sample]:
    records = json.loads(dataset_json.read_text(encoding="utf-8"))
    samples = []
    seen_ids = set()
    for record in records:
        image_path = Path(record["images"][0])
        if not image_path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")

        sample_id = image_path.stem
        if sample_id in seen_ids:
            raise ValueError(f"Duplicate test sample id: {sample_id}")

        seen_ids.add(sample_id)
        samples.append(
            Sample(
                image_path=image_path,
                sample_id=sample_id,
                user_content=record["messages"][0]["content"],
            )
        )
        if limit is not None and len(samples) >= limit:
            break

    return samples


def iter_balanced(text: str, opening: str, closing: str):
    depth = 0
    start = None
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == opening:
            if depth == 0:
                start = index
            depth += 1
        elif char == closing and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : index + 1]
                start = None


def normalize_prediction(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, dict):
        return None

    defect_type = value.get("defect_type") or value.get("type") or value.get("label")
    ellipses = value.get("ellipses")
    if not isinstance(defect_type, str) or not defect_type.strip() or not isinstance(ellipses, list):
        return None

    normalized = []
    for ellipse in ellipses:
        if not isinstance(ellipse, dict):
            continue
        if any(field not in ellipse for field in ELLIPSE_FIELDS):
            continue
        if any(
            isinstance(ellipse[field], bool) or not isinstance(ellipse[field], (int, float))
            for field in ELLIPSE_FIELDS
        ):
            continue
        if ellipse["diameter_x"] <= 0 or ellipse["diameter_y"] <= 0:
            continue
        normalized.append({field: float(ellipse[field]) for field in ELLIPSE_FIELDS})

    if not normalized:
        return None
    return {"defect_type": defect_type.strip(), "ellipses": normalized}


def parse_prediction(text: str) -> dict[str, Any] | None:
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    candidates = fenced + list(iter_balanced(text, "{", "}")) + list(iter_balanced(text, "[", "]"))
    for candidate in candidates:
        try:
            value = json.loads(candidate.strip())
        except (json.JSONDecodeError, AttributeError):
            continue
        prediction = normalize_prediction(value)
        if prediction is not None:
            return prediction
    return None


def load_model_and_processor(model_path: Path, load_in_8bit: bool) -> tuple[Any, Any]:
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
    model_kwargs: dict[str, Any] = {
        "device_map": "auto",
        "trust_remote_code": True,
        "torch_dtype": "auto",
    }
    if load_in_8bit:
        model_kwargs["load_in_8bit"] = True
    model = AutoModelForImageTextToText.from_pretrained(model_path, **model_kwargs)
    model.eval()
    return model, processor


def move_inputs_to_device(inputs: dict[str, Any], model: Any) -> dict[str, Any]:
    if hasattr(model, "hf_device_map"):
        return inputs
    device = next(model.parameters()).device
    return {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}


def generate_text(model: Any, processor: Any, sample: Sample, max_new_tokens: int) -> str:
    import torch
    from PIL import Image

    image = Image.open(sample.image_path).convert("RGB")
    content = []
    remaining = sample.user_content
    while "<image>" in remaining:
        before, remaining = remaining.split("<image>", 1)
        if before:
            content.append({"type": "text", "text": before})
        content.append({"type": "image", "image": image})
    if remaining:
        content.append({"type": "text", "text": remaining})

    messages = [{"role": "user", "content": content}]
    try:
        inputs = processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
    except TypeError:
        prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[prompt], images=[image], return_tensors="pt")

    inputs = move_inputs_to_device(inputs, model)
    input_length = inputs["input_ids"].shape[-1]
    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=getattr(processor.tokenizer, "pad_token_id", None),
            eos_token_id=getattr(processor.tokenizer, "eos_token_id", None),
        )
    return processor.batch_decode(generated[:, input_length:], skip_special_tokens=True)[0].strip()


def release_model(model: Any, processor: Any) -> None:
    del model
    del processor
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        pass


def run_one_model(
    name: str,
    model_path: Path,
    samples: list[Sample],
    output_dir: Path,
    max_new_tokens: int,
    load_in_8bit: bool,
) -> None:
    model, processor = load_model_and_processor(model_path, load_in_8bit)
    model_dir = output_dir / name
    records = []
    try:
        for index, sample in enumerate(samples, start=1):
            print(f"[{name}] {index}/{len(samples)} {sample.sample_id}", flush=True)
            raw_text = generate_text(model, processor, sample, max_new_tokens)
            prediction = parse_prediction(raw_text)
            text_path = model_dir / "texts" / f"{sample.sample_id}.txt"
            json_path = model_dir / "json" / f"{sample.sample_id}.json"
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(raw_text + "\n", encoding="utf-8")
            write_json(prediction, json_path)
            records.append(
                {
                    "sample_id": sample.sample_id,
                    "image": sample.image_path.as_posix(),
                    "user_content": sample.user_content,
                    "raw_text": raw_text,
                    "prediction": prediction,
                    "parse_failed": prediction is None,
                }
            )
            write_json(records, model_dir / "predictions.json")
    finally:
        release_model(model, processor)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Qwen3.6-27B before and after PCB X-ray LoRA tuning.")
    parser.add_argument("--base-model", type=Path, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--tuned-model", type=Path, default=DEFAULT_TUNED_MODEL)
    parser.add_argument("--dataset-json", type=Path, default=DEFAULT_DATASET_JSON)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=0, help="Number of samples; 0 means all test samples.")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--load-in-8bit", action="store_true")
    parser.add_argument("--skip-base", action="store_true", help="Only run the merged LoRA model.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    limit = None if args.limit == 0 else args.limit
    samples = read_dataset_json(args.dataset_json, limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.skip_base:
        run_one_model(
            "before_lora",
            args.base_model,
            samples,
            args.output_dir,
            args.max_new_tokens,
            args.load_in_8bit,
        )
    run_one_model(
        "after_lora",
        args.tuned_model,
        samples,
        args.output_dir,
        args.max_new_tokens,
        args.load_in_8bit,
    )
    print(f"Inference complete. Results saved to {args.output_dir}")


if __name__ == "__main__":
    main()
