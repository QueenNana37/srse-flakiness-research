import sys
import pandas as pd
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel, AutoConfig
from codebert_model import BERT_Arch

# Matches the print order in rq1.sh's output: Async, Conc, Time, UC, OD, Non-flaky
CATEGORY_MAP = {
    0: "Async Wait",
    1: "Concurrency",
    2: "Time",
    3: "Unordered Collections",
    4: "Order Dependent",
    5: "Not Flaky",
}


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 infer_flakeflagger.py <input_csv> <output_csv> [model_fold=1]")
        sys.exit(1)

    input_csv = sys.argv[1]
    output_csv = sys.argv[2]
    model_fold = sys.argv[3] if len(sys.argv) > 3 else "1"

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    model_name = "microsoft/codebert-base"
    config = AutoConfig.from_pretrained(model_name, return_dict=False, output_hidden_states=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    auto_model = AutoModel.from_pretrained(model_name, config=config)

    model = BERT_Arch(auto_model, output_layer=6)
    weights_path = f"../models/per_project_model_weights_on__dataset_project_group_{model_fold}.pt"
    print(f"Loading weights from {weights_path}")
    model.load_state_dict(torch.load(weights_path, map_location=device))
    model.to(device)
    model.eval()

    df = pd.read_csv(input_csv)
    print(f"Loaded {len(df)} rows from {input_csv}")

    predictions = []
    predicted_categories = []
    confidences = []

    with torch.no_grad():
        for i, code in enumerate(df["full_code"]):
            tokens = tokenizer.batch_encode_plus(
                [str(code)], max_length=512, pad_to_max_length=True, truncation=True
            )
            seq = torch.tensor(tokens["input_ids"]).to(device).long()
            mask = torch.tensor(tokens["attention_mask"]).to(device).long()

            logits = model(seq, mask)
            probs = F.softmax(logits, dim=1)
            pred_class = int(torch.argmax(probs, dim=1).item())
            confidence = float(torch.max(probs).item())

            predictions.append(pred_class)
            predicted_categories.append(CATEGORY_MAP[pred_class])
            confidences.append(confidence)

            print(f"[{i + 1}/{len(df)}] {CATEGORY_MAP[pred_class]} (confidence={confidence:.2f})")

    df["predicted_label"] = predictions
    df["predicted_category"] = predicted_categories
    df["confidence"] = confidences
    df.to_csv(output_csv, index=False)
    print(f"\nSaved predictions to {output_csv}")


if __name__ == "__main__":
    main()
